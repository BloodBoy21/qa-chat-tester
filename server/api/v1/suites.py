import json
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from lib.mongo import db
from db.repositories.test_suite_repository import TestSuiteRepository
from db.repositories.test_case_repository import TestCaseRepository
from server.api.v1.deps import get_account_id
from server.api.v1.pagination import make_page

router = APIRouter(prefix="/suites", tags=["suites"])


# ── helpers ───────────────────────────────────────────────────────────────────

def _suites() -> TestSuiteRepository:
    return TestSuiteRepository(db["test_suites"])


def _cases() -> TestCaseRepository:
    return TestCaseRepository(db["test_cases"])


def _serialize_dt(doc: dict) -> dict:
    for field in ("created_at", "updated_at"):
        val = doc.get(field)
        if hasattr(val, "strftime"):
            doc[field] = val.strftime("%Y-%m-%dT%H:%M:%SZ")
    return doc


def _suite_or_404(suite_id: str, account_id: str) -> dict:
    suite = _suites().get(suite_id, account_id)
    if not suite:
        raise HTTPException(status_code=404, detail="Suite not found")
    return suite


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class SuiteCreate(BaseModel):
    title: str
    description: str | None = None


class SuiteUpdate(BaseModel):
    title: str | None = None
    description: str | None = None


class CaseCreate(BaseModel):
    title: str
    description: str | None = None
    payload: dict


class CaseUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    payload: dict | None = None


# ── Suite CRUD ────────────────────────────────────────────────────────────────

@router.get("")
async def list_suites(
    account_id: str = Depends(get_account_id),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    col = db["test_suites"]
    total = col.count_documents({"account_id": account_id})
    skip = (page - 1) * page_size
    docs = list(
        col.find({"account_id": account_id})
        .sort("created_at", -1)
        .skip(skip)
        .limit(page_size)
    )
    case_repo = _cases()
    items = []
    for doc in docs:
        from db.repositories.base import BaseMongoRepository
        doc["_id"] = str(doc["_id"])
        _serialize_dt(doc)
        doc["case_count"] = case_repo.count_by_suite(doc["_id"], account_id)
        items.append(doc)
    return make_page(items, total, page, page_size)


@router.post("", status_code=201)
async def create_suite(
    body: SuiteCreate,
    account_id: str = Depends(get_account_id),
):
    suite = _suites().create(
        account_id=account_id,
        title=body.title,
        description=body.description,
    )
    return _serialize_dt(suite)


@router.get("/{suite_id}")
async def get_suite(suite_id: str, account_id: str = Depends(get_account_id)):
    suite = _suite_or_404(suite_id, account_id)
    _serialize_dt(suite)
    suite["case_count"] = _cases().count_by_suite(suite_id, account_id)
    return suite


@router.patch("/{suite_id}")
async def update_suite(
    suite_id: str,
    body: SuiteUpdate,
    account_id: str = Depends(get_account_id),
):
    _suite_or_404(suite_id, account_id)
    updated = _suites().update(suite_id, account_id, **body.model_dump(exclude_none=True))
    return _serialize_dt(updated)


@router.delete("/{suite_id}", status_code=200)
async def delete_suite(suite_id: str, account_id: str = Depends(get_account_id)):
    _suite_or_404(suite_id, account_id)
    deleted_cases = _cases().delete_by_suite(suite_id, account_id)
    _suites().delete(suite_id, account_id)
    return {"ok": True, "deleted_cases": deleted_cases}


# ── Cases within a suite ──────────────────────────────────────────────────────

@router.get("/{suite_id}/cases")
async def list_cases(
    suite_id: str,
    account_id: str = Depends(get_account_id),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
):
    _suite_or_404(suite_id, account_id)
    col = db["test_cases"]
    query = {"suite_id": suite_id, "account_id": account_id}
    total = col.count_documents(query)
    skip = (page - 1) * page_size
    docs = list(col.find(query).sort("created_at", 1).skip(skip).limit(page_size))
    items = []
    for doc in docs:
        doc["_id"] = str(doc["_id"])
        _serialize_dt(doc)
        items.append(doc)
    return make_page(items, total, page, page_size)


@router.post("/{suite_id}/cases", status_code=201)
async def create_case(
    suite_id: str,
    body: CaseCreate,
    account_id: str = Depends(get_account_id),
):
    _suite_or_404(suite_id, account_id)
    case = _cases().create(
        account_id=account_id,
        suite_id=suite_id,
        title=body.title,
        description=body.description,
        payload=body.payload,
    )
    return _serialize_dt(case)


@router.post("/{suite_id}/cases/upload", status_code=201)
async def upload_cases(
    suite_id: str,
    file: UploadFile = File(...),
    account_id: str = Depends(get_account_id),
    replace: bool = Query(True, description="Replace existing cases in the suite"),
):
    """
    Upload a JSON file to bulk-insert cases into a suite.

    The file must be a JSON array. Each element can be:
    - `{ "title": "...", "description": "...", "payload": { ... } }`  (structured)
    - Any dict — treated as the payload directly, title auto-generated as "Case N"
    """
    _suite_or_404(suite_id, account_id)

    raw = await file.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"JSON inválido: {exc}")

    if not isinstance(data, list):
        raise HTTPException(
            status_code=400,
            detail="El archivo debe contener un array JSON en el nivel raíz",
        )

    inserted = _cases().bulk_create(
        account_id=account_id,
        suite_id=suite_id,
        items=data,
        replace=replace,
    )
    return {
        "ok": True,
        "inserted": inserted,
        "total": _cases().count_by_suite(suite_id, account_id),
    }
