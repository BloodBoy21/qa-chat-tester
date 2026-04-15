import json
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from lib.mongo import db
from server.api.v1.deps import get_account_id
from server.api.v1.xlsx import build_xlsx

router = APIRouter()


def _parse_campaigns(value) -> str:
    if not value:
        return ""
    camps = value if isinstance(value, list) else []
    if not camps:
        try:
            camps = json.loads(value) if isinstance(value, str) else []
        except Exception:
            return ""
    return " | ".join(
        c.get("campaign_name", c.get("campaign_id", str(c)))
        for c in camps
        if isinstance(c, dict)
    )


def _fmt_dt(val) -> str:
    if val is None:
        return ""
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(val)


@router.get("/export/conversations")
async def export_conversations(account_id: str = Depends(get_account_id)):
    pipeline = [
        {"$match": {"account_id": account_id, "message": {"$ne": None}}},
        {"$sort": {"run_id": 1, "created_at": 1}},
        # join insight by run_id
        {"$lookup": {
            "from": "insights",
            "let": {"rid": "$run_id"},
            "pipeline": [
                {"$match": {"$expr": {"$and": [
                    {"$eq": ["$run_id", "$$rid"]},
                    {"$eq": ["$account_id", account_id]},
                ]}}},
                {"$limit": 1},
                {"$project": {"_id": 0, "analysis": 1, "complete": 1}},
            ],
            "as": "_insight",
        }},
        # join case by run_id
        {"$lookup": {
            "from": "cases",
            "let": {"rid": "$run_id"},
            "pipeline": [
                {"$match": {"$expr": {"$and": [
                    {"$eq": ["$run_id", "$$rid"]},
                    {"$eq": ["$account_id", account_id]},
                ]}}},
                {"$limit": 1},
                {"$project": {"_id": 0, "payload": 1}},
            ],
            "as": "_case",
        }},
        {"$addFields": {
            "analysis": {"$arrayElemAt": ["$_insight.analysis", 0]},
            "complete": {"$arrayElemAt": ["$_insight.complete", 0]},
            "case_payload": {"$arrayElemAt": ["$_case.payload", 0]},
        }},
        {"$project": {"_insight": 0, "_case": 0}},
    ]

    rows = list(db["logs"].aggregate(pipeline))

    headers = [
        "session_id", "run_id", "user_id", "scenario_group_id", "scenario",
        "message", "response", "campaign", "analysis", "complete",
        "created_at", "test_case",
    ]

    data = []
    for r in rows:
        payload = r.get("case_payload")
        test_case = (
            json.dumps(payload, ensure_ascii=False, indent=2)
            if payload
            else ""
        )
        data.append([
            r.get("session_id", ""),
            r.get("run_id", ""),
            r.get("user_id", ""),
            r.get("scenario_group_id", ""),
            r.get("scenario", ""),
            r.get("message", ""),
            r.get("response", ""),
            _parse_campaigns(r.get("campaigns")),
            r.get("analysis", ""),
            "SI" if r.get("complete") else "NO",
            _fmt_dt(r.get("created_at")),
            test_case,
        ])

    xlsx_bytes = build_xlsx(headers, data)
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="conversaciones.xlsx"'},
    )
