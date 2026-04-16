import asyncio
import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from loguru import logger

from lib.mongo import db
from server.api.v1.deps import get_account_id

router = APIRouter()

DEFAULT_MODEL = os.getenv("MODEL_NAME", "gemini-2.5-flash")


# ── helpers ───────────────────────────────────────────────────────────────────

def _parse_campaigns(value) -> list:
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _fmt(doc: dict) -> dict:
    for field in ("created_at", "updated_at"):
        val = doc.get(field)
        if hasattr(val, "strftime"):
            doc[field] = val.strftime("%Y-%m-%dT%H:%M:%SZ")
    return doc


# ── schemas ───────────────────────────────────────────────────────────────────

class InsightUpdate(BaseModel):
    complete: bool | None = None
    analysis: str | None = None


class AnalyseRequest(BaseModel):
    model: str | None = None


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.get("/conversations")
async def list_conversations(account_id: str = Depends(get_account_id)):
    pipeline = [
        {"$match": {"account_id": account_id}},
        {"$sort": {"created_at": 1}},
        {"$group": {
            "_id": "$session_id",
            "run_id": {"$first": "$run_id"},
            "scenario_group_id": {"$first": "$scenario_group_id"},
            "scenario": {"$first": "$scenario"},
            "user_id": {"$first": "$user_id"},
            "message_count": {"$sum": 1},
            "started_at": {"$min": "$created_at"},
            "last_message_at": {"$max": "$created_at"},
            "campaigns": {
                "$first": {
                    "$cond": [
                        {"$and": [
                            {"$ne": ["$campaigns", None]},
                            {"$ne": ["$campaigns", []]},
                        ]},
                        "$campaigns",
                        "$$REMOVE",
                    ]
                }
            },
        }},
        {"$lookup": {
            "from": "insights",
            "let": {"sid": "$_id"},
            "pipeline": [
                {"$match": {"$expr": {"$and": [
                    {"$eq": ["$session_id", "$$sid"]},
                    {"$eq": ["$account_id", account_id]},
                ]}}},
                {"$sort": {"created_at": -1}},
                {"$limit": 1},
                {"$project": {
                    "_id": 0,
                    "complete": 1,
                    "analysis": {"$substr": ["$analysis", 0, 120]},
                }},
            ],
            "as": "insight",
        }},
        {"$addFields": {
            "session_id": "$_id",
            "insight_complete": {"$arrayElemAt": ["$insight.complete", 0]},
            "insight_summary": {"$arrayElemAt": ["$insight.analysis", 0]},
        }},
        {"$project": {"_id": 0, "insight": 0}},
        {"$sort": {"last_message_at": -1}},
    ]

    docs = list(db["logs"].aggregate(pipeline))
    for doc in docs:
        doc["campaigns"] = _parse_campaigns(doc.get("campaigns"))
        for field in ("started_at", "last_message_at"):
            val = doc.get(field)
            if hasattr(val, "isoformat"):
                doc[field] = val.strftime("%Y-%m-%dT%H:%M:%SZ")
    return docs


@router.get("/conversations/{session_id}")
async def get_conversation(
    session_id: str,
    account_id: str = Depends(get_account_id),
):
    logs_col = db["logs"]
    insights_col = db["insights"]
    cases_col = db["cases"]

    messages_cursor = logs_col.find(
        {"session_id": session_id, "account_id": account_id},
        sort=[("created_at", 1)],
    )
    messages = []
    run_id = None
    for doc in messages_cursor:
        doc["_id"] = str(doc["_id"])
        _fmt(doc)
        if run_id is None and doc.get("run_id"):
            run_id = doc["run_id"]
        messages.append(doc)

    if not messages:
        raise HTTPException(status_code=404, detail="Conversation not found")

    insight_doc = insights_col.find_one(
        {"session_id": session_id, "account_id": account_id},
        sort=[("created_at", -1)],
    )
    if insight_doc:
        insight_doc["_id"] = str(insight_doc["_id"])
        _fmt(insight_doc)

    case_doc = None
    if run_id:
        case_doc = cases_col.find_one(
            {"run_id": run_id, "account_id": account_id},
            sort=[("created_at", 1)],
        )
        if case_doc:
            case_doc["_id"] = str(case_doc["_id"])
            _fmt(case_doc)

    return {
        "messages": messages,
        "insight": insight_doc,
        "case": case_doc,
    }


@router.patch("/conversations/{session_id}/insight")
async def update_insight(
    session_id: str,
    body: InsightUpdate,
    account_id: str = Depends(get_account_id),
):
    """
    Update or create the insight for a conversation.
    Accepts `complete` (bool) and/or `analysis` (str).
    If no insight exists yet, creates one.
    """
    if body.complete is None and body.analysis is None:
        raise HTTPException(status_code=400, detail="Provide at least 'complete' or 'analysis'")

    insights_col = db["insights"]
    now = datetime.now(timezone.utc)

    existing = insights_col.find_one(
        {"session_id": session_id, "account_id": account_id},
        sort=[("created_at", -1)],
    )

    if existing:
        to_set: dict = {"updated_at": now}
        if body.complete is not None:
            to_set["complete"] = body.complete
        if body.analysis is not None:
            to_set["analysis"] = body.analysis
        insights_col.update_one({"_id": existing["_id"]}, {"$set": to_set})
    else:
        # No insight yet — create one
        # Try to pull run_id from logs
        log = db["logs"].find_one(
            {"session_id": session_id, "account_id": account_id},
            sort=[("created_at", -1)],
            projection={"run_id": 1},
        )
        insights_col.insert_one({
            "session_id": session_id,
            "account_id": account_id,
            "run_id": log.get("run_id") if log else None,
            "complete": body.complete if body.complete is not None else False,
            "analysis": body.analysis or "",
            "created_at": now,
            "updated_at": now,
        })

    updated = insights_col.find_one(
        {"session_id": session_id, "account_id": account_id},
        sort=[("created_at", -1)],
    )
    updated["_id"] = str(updated["_id"])
    _fmt(updated)
    updated["complete"] = bool(updated.get("complete", False))
    return updated


@router.post("/conversations/{session_id}/analyse", status_code=202)
async def trigger_analysis(
    session_id: str,
    body: AnalyseRequest = AnalyseRequest(),
    account_id: str = Depends(get_account_id),
):
    """
    Trigger a background manual analysis for a conversation.
    Returns immediately (202); poll GET /conversations/{session_id} to see
    when the insight appears or updates.
    """
    # Verify conversation exists
    log = db["logs"].find_one(
        {"session_id": session_id, "account_id": account_id},
        sort=[("created_at", -1)],
        projection={"run_id": 1, "user_id": 1},
    )
    if not log:
        raise HTTPException(status_code=404, detail="Conversation not found")

    run_id = log.get("run_id") or session_id
    user_id = log.get("user_id", "default_user")
    model = body.model or DEFAULT_MODEL

    # Fetch case context for the run (best-effort)
    case_doc = db["cases"].find_one(
        {"run_id": run_id, "account_id": account_id},
        projection={"payload": 1},
    )
    context = json.dumps(case_doc["payload"]) if case_doc and case_doc.get("payload") else "{}"

    asyncio.create_task(
        _run_analysis_background(
            session_id=session_id,
            run_id=run_id,
            user_id=user_id,
            context=context,
            model=model,
            account_id=account_id,
        )
    )

    return {"ok": True, "status": "queued", "session_id": session_id}


# ── background analysis ───────────────────────────────────────────────────────

async def _run_analysis_background(
    session_id: str,
    run_id: str,
    user_id: str,
    context: str,
    model: str,
    account_id: str,
) -> None:
    try:
        from lib.agent_loop import run_analysis_agent_manual
        logger.info(f"[analyse] Starting manual analysis for session={session_id} account={account_id}")
        await run_analysis_agent_manual(
            run_id=run_id,
            context=context,
            user_id=user_id,
            model=model,
            account_id=account_id,
        )
        logger.info(f"[analyse] Done for session={session_id}")
    except Exception as e:
        logger.error(f"[analyse] Failed for session={session_id}: {e}")
