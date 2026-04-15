from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from lib.mongo import db
from db.repositories.test_case_repository import TestCaseRepository
from server.api.v1.deps import get_account_id

router = APIRouter(prefix="/cases", tags=["cases"])


def _repo() -> TestCaseRepository:
    return TestCaseRepository(db["test_cases"])


def _serialize_dt(doc: dict) -> dict:
    for field in ("created_at", "updated_at"):
        val = doc.get(field)
        if hasattr(val, "strftime"):
            doc[field] = val.strftime("%Y-%m-%dT%H:%M:%SZ")
    return doc


class CaseUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    payload: dict | None = None


@router.get("/{case_id}")
async def get_case(case_id: str, account_id: str = Depends(get_account_id)):
    case = _repo().get(case_id, account_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return _serialize_dt(case)


@router.patch("/{case_id}")
async def update_case(
    case_id: str,
    body: CaseUpdate,
    account_id: str = Depends(get_account_id),
):
    repo = _repo()
    if not repo.get(case_id, account_id):
        raise HTTPException(status_code=404, detail="Case not found")
    updated = repo.update(case_id, account_id, **body.model_dump(exclude_none=True))
    return _serialize_dt(updated)


@router.delete("/{case_id}", status_code=200)
async def delete_case(case_id: str, account_id: str = Depends(get_account_id)):
    deleted = _repo().delete(case_id, account_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Case not found")
    return {"ok": True}
