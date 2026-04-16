import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from lib.mongo import db
from db.repositories.run_repository import RunRepository
from db.repositories.test_suite_repository import TestSuiteRepository
from db.repositories.test_case_repository import TestCaseRepository
from server.api.v1.deps import get_account_id
from server.api.v1.pagination import make_page

router = APIRouter(prefix="/runs", tags=["runs"])

DEFAULT_MODEL = os.getenv("MODEL_NAME", "gemini-2.5-flash")


# ── helpers ───────────────────────────────────────────────────────────────────

def _runs() -> RunRepository:
    return RunRepository(db["runs"])


def _suites() -> TestSuiteRepository:
    return TestSuiteRepository(db["test_suites"])


def _cases() -> TestCaseRepository:
    return TestCaseRepository(db["test_cases"])


def _serialize_run(run: dict) -> dict:
    for field in ("created_at", "started_at", "finished_at"):
        val = run.get(field)
        if hasattr(val, "strftime"):
            run[field] = val.strftime("%Y-%m-%dT%H:%M:%SZ")
    return run


def _get_or_404(run_id: str, account_id: str) -> dict:
    run = _runs().get(run_id, account_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


# ── schemas ───────────────────────────────────────────────────────────────────

class RunSuiteRequest(BaseModel):
    model: str | None = None
    case_ids: list[str] | None = None   # None = run all cases in suite


class RunCaseRequest(BaseModel):
    model: str | None = None


# ── list / detail ─────────────────────────────────────────────────────────────

@router.get("")
async def list_runs(
    account_id: str = Depends(get_account_id),
    suite_id: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
):
    col = db["runs"]
    query = {"account_id": account_id}
    if suite_id:
        query["suite_id"] = suite_id
    total = col.count_documents(query)
    skip = (page - 1) * page_size
    docs = list(col.find(query).sort("created_at", -1).skip(skip).limit(page_size))
    items = [_serialize_run(r) for r in (_runs()._serialize(d) for d in docs)]
    return make_page(items, total, page, page_size)


@router.get("/{run_id}")
async def get_run(run_id: str, account_id: str = Depends(get_account_id)):
    return _serialize_run(_get_or_404(run_id, account_id))


# ── trigger ───────────────────────────────────────────────────────────────────

@router.post("/suite/{suite_id}", status_code=202)
async def trigger_suite_run(
    suite_id: str,
    body: RunSuiteRequest = RunSuiteRequest(),
    account_id: str = Depends(get_account_id),
):
    """
    Queue execution of cases in a test suite.
    Pass `case_ids` in the body to run only a specific selection.
    """
    suite = _suites().get(suite_id, account_id)
    if not suite:
        raise HTTPException(status_code=404, detail="Suite not found")

    case_repo = _cases()

    if body.case_ids:
        # Validate every requested case belongs to this suite & account
        all_cases = case_repo.get_by_suite(suite_id, account_id)
        valid_ids = {c["_id"] for c in all_cases}
        requested = [cid for cid in body.case_ids if cid in valid_ids]
        if not requested:
            raise HTTPException(status_code=400, detail="None of the requested cases belong to this suite")
        total = len(requested)
        run_type = "selection"
    else:
        total = case_repo.count_by_suite(suite_id, account_id)
        if total == 0:
            raise HTTPException(status_code=400, detail="Suite has no test cases")
        requested = None
        run_type = "suite"

    model = body.model or DEFAULT_MODEL
    run_id = str(uuid.uuid4())

    _runs().create(
        run_id=run_id,
        account_id=account_id,
        run_type=run_type,
        total_cases=total,
        model=model,
        suite_id=suite_id,
        case_ids=requested,
    )

    from celery_queue.jobs.tasks import run_suite
    run_suite.delay(
        run_id=run_id,
        suite_id=suite_id,
        account_id=account_id,
        model=model,
        case_ids=requested,
    )

    return {
        "run_id": run_id,
        "status": "pending",
        "total_cases": total,
        "suite_id": suite_id,
        "model": model,
        "case_ids": requested,
    }


@router.post("/case/{case_id}", status_code=202)
async def trigger_case_run(
    case_id: str,
    body: RunCaseRequest = RunCaseRequest(),
    account_id: str = Depends(get_account_id),
):
    """Queue execution of a single test case."""
    case = _cases().get(case_id, account_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    model = body.model or DEFAULT_MODEL
    run_id = str(uuid.uuid4())

    _runs().create(
        run_id=run_id,
        account_id=account_id,
        run_type="case",
        total_cases=1,
        model=model,
        suite_id=case.get("suite_id"),
        case_id=case_id,
    )

    from celery_queue.jobs.tasks import run_case
    run_case.delay(run_id=run_id, case_id=case_id, account_id=account_id, model=model)

    return {"run_id": run_id, "status": "pending", "total_cases": 1, "case_id": case_id, "model": model}


# ── control ───────────────────────────────────────────────────────────────────

@router.post("/{run_id}/pause")
async def pause_run(run_id: str, account_id: str = Depends(get_account_id)):
    run = _get_or_404(run_id, account_id)
    if run["status"] != RunRepository.STATUS_RUNNING:
        raise HTTPException(status_code=409, detail=f"Run is '{run['status']}', not running")
    _runs().mark_paused(run_id)
    return {"ok": True, "status": RunRepository.STATUS_PAUSED}


@router.post("/{run_id}/resume")
async def resume_run(run_id: str, account_id: str = Depends(get_account_id)):
    run = _get_or_404(run_id, account_id)
    if run["status"] != RunRepository.STATUS_PAUSED:
        raise HTTPException(status_code=409, detail=f"Run is '{run['status']}', not paused")
    _runs().mark_resumed(run_id)
    return {"ok": True, "status": RunRepository.STATUS_RUNNING}


@router.post("/{run_id}/stop")
async def stop_run(run_id: str, account_id: str = Depends(get_account_id)):
    run = _get_or_404(run_id, account_id)
    if run["status"] not in RunRepository.CONTROLLABLE:
        raise HTTPException(status_code=409, detail=f"Run is already '{run['status']}'")
    _runs().mark_stopped(run_id)
    return {"ok": True, "status": RunRepository.STATUS_STOPPED}
