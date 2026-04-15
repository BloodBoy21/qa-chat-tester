import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from lib.mongo import db
from db.repositories.run_repository import RunRepository
from db.repositories.test_suite_repository import TestSuiteRepository
from db.repositories.test_case_repository import TestCaseRepository
from server.api.v1.deps import get_account_id

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


# ── schemas ───────────────────────────────────────────────────────────────────

class RunSuiteRequest(BaseModel):
    model: str | None = None


class RunCaseRequest(BaseModel):
    model: str | None = None


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_runs(
    account_id: str = Depends(get_account_id),
    suite_id: str = Query(None, description="Filter by suite"),
    limit: int = Query(50, ge=1, le=200),
):
    runs = _runs().get_all(account_id, limit=limit, suite_id=suite_id)
    return [_serialize_run(r) for r in runs]


@router.get("/{run_id}")
async def get_run(run_id: str, account_id: str = Depends(get_account_id)):
    run = _runs().get(run_id, account_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return _serialize_run(run)


@router.post("/suite/{suite_id}", status_code=202)
async def trigger_suite_run(
    suite_id: str,
    body: RunSuiteRequest = RunSuiteRequest(),
    account_id: str = Depends(get_account_id),
):
    """Queue execution of all cases in a test suite."""
    # Validate suite exists and has cases
    suite = _suites().get(suite_id, account_id)
    if not suite:
        raise HTTPException(status_code=404, detail="Suite not found")

    total = _cases().count_by_suite(suite_id, account_id)
    if total == 0:
        raise HTTPException(status_code=400, detail="Suite has no test cases")

    model = body.model or DEFAULT_MODEL
    run_id = str(uuid.uuid4())

    # Persist the run record before dispatching so the caller can poll immediately
    _runs().create(
        run_id=run_id,
        account_id=account_id,
        run_type="suite",
        total_cases=total,
        model=model,
        suite_id=suite_id,
    )

    # Dispatch Celery task — import here to avoid circular imports at startup
    from celery_queue.jobs.tasks import run_suite
    run_suite.delay(
        run_id=run_id,
        suite_id=suite_id,
        account_id=account_id,
        model=model,
    )

    return {
        "run_id": run_id,
        "status": "pending",
        "total_cases": total,
        "suite_id": suite_id,
        "model": model,
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
    run_case.delay(
        run_id=run_id,
        case_id=case_id,
        account_id=account_id,
        model=model,
    )

    return {
        "run_id": run_id,
        "status": "pending",
        "total_cases": 1,
        "case_id": case_id,
        "model": model,
    }
