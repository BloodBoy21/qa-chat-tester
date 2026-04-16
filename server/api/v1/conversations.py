import asyncio
import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from loguru import logger

from lib.mongo import db
from server.api.v1.deps import get_account_id
from server.api.v1.pagination import make_page

router = APIRouter()

DEFAULT_MODEL = os.getenv("MODEL_NAME", "gemini-2.5-flash")


def _parse_campaigns(value) -> list:
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        return json.loads(value) or []
    except Exception:
        return []


def _fmt(doc: dict) -> dict:
    for field in ("created_at", "updated_at"):
        val = doc.get(field)
        if hasattr(val, "strftime"):
            doc[field] = val.strftime("%Y-%m-%dT%H:%M:%SZ")
    return doc


class InsightUpdate(BaseModel):
    complete: bool | None = None
    analysis: str | None = None


class AnalyseRequest(BaseModel):
    model: str | None = None


@router.get("/conversations")
async def list_conversations(
    account_id: str = Depends(get_account_id),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: str = Query("all", description="all | done | pend"),
    objective: str = Query("all", description="all | ok | fail"),
    run_filter: str = Query("", description="Suite run_id to filter conversations"),
    search_field: str = Query("session_id"),
    search_query: str = Query(""),
):
    skip = (page - 1) * page_size

    # Initial match on logs
    match: dict = {"account_id": account_id}

    # Filter by suite run — resolve conversation_run_ids from the runs collection
    if run_filter:
        run_doc = db["runs"].find_one(
            {"run_id": run_filter, "account_id": account_id},
            projection={"conversation_run_ids": 1},
        )
        conv_ids = run_doc.get("conversation_run_ids", []) if run_doc else []
        match["run_id"] = {"$in": conv_ids} if conv_ids else {"$in": []}

    # Text search on indexed log fields
    searchable = {"session_id", "run_id", "user_id", "scenario_group_id", "scenario"}
    if search_query and search_field in searchable:
        match[search_field] = {"$regex": search_query, "$options": "i"}

    pipeline: list = [
        {"$match": match},
        {"$sort": {"created_at": 1}},
        {"$group": {
            "_id": "$session_id",
            "run_id":            {"$first": "$run_id"},
            "scenario_group_id": {"$first": "$scenario_group_id"},
            "scenario":          {"$first": "$scenario"},
            "user_id":           {"$first": "$user_id"},
            "message_count":     {"$sum": 1},
            "started_at":        {"$min": "$created_at"},
            "last_message_at":   {"$max": "$created_at"},
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
            "session_id":      "$_id",
            "insight_complete": {"$arrayElemAt": ["$insight.complete", 0]},
            "insight_summary":  {"$arrayElemAt": ["$insight.analysis", 0]},
        }},
        {"$project": {"_id": 0, "insight": 0}},
    ]

    # Post-group filters (on insight fields)
    post: dict = {}
    if status == "done":
        post["$or"] = [
            {"insight_summary": {"$ne": None}},
            {"insight_complete": {"$ne": None}},
        ]
    elif status == "pend":
        post["insight_summary"] = None
        post["insight_complete"] = None

    if objective == "ok":
        post["insight_complete"] = True
    elif objective == "fail":
        post["insight_complete"] = False

    if post:
        pipeline.append({"$match": post})

    # Facet: count + paginated items in one trip
    pipeline.append({
        "$facet": {
            "total": [{"$count": "n"}],
            "items": [
                {"$sort": {"last_message_at": -1}},
                {"$skip": skip},
                {"$limit": page_size},
            ],
        }
    })

    result = list(db["logs"].aggregate(pipeline))
    total = result[0]["total"][0]["n"] if result and result[0]["total"] else 0
    items = result[0]["items"] if result else []

    for doc in items:
        doc["campaigns"] = _parse_campaigns(doc.get("campaigns"))
        for field in ("started_at", "last_message_at"):
            val = doc.get(field)
            if hasattr(val, "isoformat"):
                doc[field] = val.strftime("%Y-%m-%dT%H:%M:%SZ")

    return make_page(items, total, page, page_size)


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
        insight_doc["complete"] = bool(insight_doc.get("complete", False))

    case_doc = None
    if run_id:
        case_doc = cases_col.find_one(
            {"run_id": run_id, "account_id": account_id},
            sort=[("created_at", 1)],
        )
        if case_doc:
            case_doc["_id"] = str(case_doc["_id"])
            _fmt(case_doc)

    return {"messages": messages, "insight": insight_doc, "case": case_doc}


@router.patch("/conversations/{session_id}/insight")
async def update_insight(
    session_id: str,
    body: InsightUpdate,
    account_id: str = Depends(get_account_id),
):
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


async def _run_analysis_background(
    session_id: str, run_id: str, user_id: str, context: str, model: str, account_id: str,
) -> None:
    try:
        from lib.agent_loop import run_analysis_agent_manual
        logger.info(f"[analyse] Starting for session={session_id} account={account_id}")
        await run_analysis_agent_manual(
            run_id=run_id, context=context, user_id=user_id, model=model, account_id=account_id,
        )
        logger.info(f"[analyse] Done for session={session_id}")
    except Exception as e:
        logger.error(f"[analyse] Failed for session={session_id}: {e}")
