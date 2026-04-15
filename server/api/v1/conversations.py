import json
from fastapi import APIRouter, Depends, HTTPException
from lib.mongo import db
from server.api.v1.deps import get_account_id

router = APIRouter()


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
            # first non-null campaigns value
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
        # convert datetime to string for JSON serialization
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
        for field in ("created_at", "updated_at"):
            if hasattr(doc.get(field), "isoformat"):
                doc[field] = doc[field].strftime("%Y-%m-%dT%H:%M:%SZ")
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
        for field in ("created_at", "updated_at"):
            if hasattr(insight_doc.get(field), "isoformat"):
                insight_doc[field] = insight_doc[field].strftime("%Y-%m-%dT%H:%M:%SZ")

    case_doc = None
    if run_id:
        case_doc = cases_col.find_one(
            {"run_id": run_id, "account_id": account_id},
            sort=[("created_at", 1)],
        )
        if case_doc:
            case_doc["_id"] = str(case_doc["_id"])
            for field in ("created_at", "updated_at"):
                if hasattr(case_doc.get(field), "isoformat"):
                    case_doc[field] = case_doc[field].strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "messages": messages,
        "insight": insight_doc,
        "case": case_doc,
    }


