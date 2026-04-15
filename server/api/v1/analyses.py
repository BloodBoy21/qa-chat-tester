from fastapi import APIRouter, Depends
from lib.mongo import db
from server.api.v1.deps import get_account_id

router = APIRouter()


@router.get("/analyses")
async def list_analyses(account_id: str = Depends(get_account_id)):
    pipeline = [
        {"$match": {"account_id": account_id}},
        {"$sort": {"created_at": -1}},
        # grab user_id, scenario_group_id, scenario, campaigns from the first log in the session
        {"$lookup": {
            "from": "logs",
            "let": {"sid": "$session_id"},
            "pipeline": [
                {"$match": {"$expr": {"$and": [
                    {"$eq": ["$session_id", "$$sid"]},
                    {"$eq": ["$account_id", account_id]},
                ]}}},
                {"$sort": {"created_at": 1}},
                {"$limit": 1},
                {"$project": {
                    "_id": 0,
                    "user_id": 1,
                    "scenario_group_id": 1,
                    "scenario": 1,
                    "campaigns": 1,
                }},
            ],
            "as": "_first_log",
        }},
        # count messages for the session
        {"$lookup": {
            "from": "logs",
            "let": {"sid": "$session_id"},
            "pipeline": [
                {"$match": {"$expr": {"$and": [
                    {"$eq": ["$session_id", "$$sid"]},
                    {"$eq": ["$account_id", account_id]},
                ]}}},
                {"$count": "n"},
            ],
            "as": "_count",
        }},
        {"$addFields": {
            "user_id": {"$arrayElemAt": ["$_first_log.user_id", 0]},
            "scenario_group_id": {"$arrayElemAt": ["$_first_log.scenario_group_id", 0]},
            "scenario": {"$arrayElemAt": ["$_first_log.scenario", 0]},
            "campaigns": {"$arrayElemAt": ["$_first_log.campaigns", 0]},
            "message_count": {"$ifNull": [{"$arrayElemAt": ["$_count.n", 0]}, 0]},
        }},
        {"$project": {"_first_log": 0, "_count": 0}},
    ]

    docs = list(db["insights"].aggregate(pipeline))
    for doc in docs:
        doc["_id"] = str(doc["_id"])
        for field in ("created_at", "updated_at"):
            if hasattr(doc.get(field), "isoformat"):
                doc[field] = doc[field].strftime("%Y-%m-%dT%H:%M:%SZ")
        if not isinstance(doc.get("campaigns"), list):
            doc["campaigns"] = []
    return docs
