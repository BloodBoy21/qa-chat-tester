from fastapi import APIRouter, Depends, Query
from lib.mongo import db
from server.api.v1.deps import get_account_id
from server.api.v1.pagination import make_page

router = APIRouter()


@router.get("/analyses")
async def list_analyses(
    account_id: str = Depends(get_account_id),
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=200),
    status: str = Query("all", description="all | ok | fail | pending"),
    group: str = Query("", description="Filter by scenario_group_id"),
    search: str = Query("", description="Text search in analysis field"),
):
    skip = (page - 1) * page_size

    # Base match on insights
    match: dict = {"account_id": account_id}
    if status == "ok":
        match["complete"] = True
    elif status == "fail":
        match["complete"] = False
    elif status == "pending":
        match["complete"] = {"$nin": [True, False]}

    if search:
        match["analysis"] = {"$regex": search, "$options": "i"}

    # Build pipeline
    pipeline: list = [
        {"$match": match},
        {"$sort": {"created_at": -1}},
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
            "user_id":           {"$arrayElemAt": ["$_first_log.user_id", 0]},
            "scenario_group_id": {"$arrayElemAt": ["$_first_log.scenario_group_id", 0]},
            "scenario":          {"$arrayElemAt": ["$_first_log.scenario", 0]},
            "campaigns":         {"$arrayElemAt": ["$_first_log.campaigns", 0]},
            "message_count":     {"$ifNull": [{"$arrayElemAt": ["$_count.n", 0]}, 0]},
        }},
        {"$project": {"_first_log": 0, "_count": 0}},
    ]

    # Group filter applied after lookup
    if group:
        pipeline.append({"$match": {"scenario_group_id": group}})

    # Facet: count + page
    pipeline.append({
        "$facet": {
            "total": [{"$count": "n"}],
            "items": [{"$skip": skip}, {"$limit": page_size}],
        }
    })

    result = list(db["insights"].aggregate(pipeline))
    total = result[0]["total"][0]["n"] if result and result[0]["total"] else 0
    items = result[0]["items"] if result else []

    for doc in items:
        doc["_id"] = str(doc["_id"])
        for field in ("created_at", "updated_at"):
            if hasattr(doc.get(field), "isoformat"):
                doc[field] = doc[field].strftime("%Y-%m-%dT%H:%M:%SZ")
        if not isinstance(doc.get("campaigns"), list):
            doc["campaigns"] = []

    # Summary counts (independent of status filter, respects search/group)
    # Used by the frontend to show accurate counts on filter buttons
    count_base: dict = {"account_id": account_id}
    if search:
        count_base["analysis"] = {"$regex": search, "$options": "i"}

    col = db["insights"]
    n_ok      = col.count_documents({**count_base, "complete": True})
    n_fail    = col.count_documents({**count_base, "complete": False})
    n_pending = col.count_documents({**count_base, "complete": {"$nin": [True, False]}})

    page_data = make_page(items, total, page, page_size)
    page_data["summary"] = {
        "ok":      n_ok,
        "fail":    n_fail,
        "pending": n_pending,
        "total":   n_ok + n_fail + n_pending,
    }
    return page_data
