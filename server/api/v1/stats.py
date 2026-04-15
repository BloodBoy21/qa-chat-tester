from fastapi import APIRouter, Depends
from lib.mongo import db
from server.api.v1.deps import get_account_id

router = APIRouter()


@router.get("/stats")
async def get_stats(account_id: str = Depends(get_account_id)):
    logs_col = db["logs"]
    insights_col = db["insights"]

    result = list(logs_col.aggregate([
        {"$match": {"account_id": account_id}},
        {"$group": {
            "_id": None,
            "messages": {"$sum": 1},
            "sessions": {"$addToSet": "$session_id"},
            "runs": {"$addToSet": "$run_id"},
        }},
        {"$project": {
            "_id": 0,
            "messages": 1,
            "sessions": {"$size": "$sessions"},
            "runs": {
                "$size": {
                    "$filter": {
                        "input": "$runs",
                        "as": "r",
                        "cond": {"$and": [
                            {"$ne": ["$$r", None]},
                            {"$ne": ["$$r", ""]},
                        ]},
                    }
                }
            },
        }},
    ]))

    insights = insights_col.count_documents({"account_id": account_id})

    if result:
        return {**result[0], "insights": insights}
    return {"messages": 0, "sessions": 0, "runs": 0, "insights": insights}
