"""
Celery tasks for running test suites and individual test cases.

Each task:
  1. Marks the Run as "running" in MongoDB
  2. Iterates over the test case payloads
  3. Calls run_agent() from main.py for each case (async → asyncio.run)
  4. Records every conversation run_id produced
  5. Marks the Run as "completed" or "failed"
"""

from __future__ import annotations

import asyncio
import traceback

from dotenv import load_dotenv

load_dotenv()

from celery_queue.config import celery_app
from lib.mongo import db
from db.repositories.test_case_repository import TestCaseRepository
from db.repositories.run_repository import RunRepository
from loguru import logger


# ── Repo helpers ──────────────────────────────────────────────────────────────

def _runs() -> RunRepository:
    return RunRepository(db["runs"])


def _test_cases() -> TestCaseRepository:
    return TestCaseRepository(db["test_cases"])


# ── Shared runner ─────────────────────────────────────────────────────────────

def _execute_cases(
    run_id: str,
    account_id: str,
    model: str,
    cases: list[dict],
) -> None:
    """
    Core loop: run each case through run_agent and track results in the Run doc.
    Runs inside a Celery worker process (sync context).
    """
    # Import here to avoid circular imports at module load time
    from main import run_agent

    run_repo = _runs()
    run_repo.mark_running(run_id)

    for i, case in enumerate(cases):
        payload = case.get("payload", case)
        user_id = payload.get("user_id", "default_user") if isinstance(payload, dict) else "default_user"
        context = payload if isinstance(payload, str) else __import__("json").dumps(payload)

        logger.info(
            f"[run={run_id}] Case {i + 1}/{len(cases)} | user_id={user_id}"
        )

        conversation_run_id = None
        failed = False
        try:
            conversation_run_id = asyncio.run(
                run_agent(
                    context=context,
                    user_id=user_id,
                    model=model,
                    item_index=i,
                    total_items=len(cases),
                    account_id=account_id,
                )
            )
        except Exception as exc:
            failed = True
            logger.error(f"[run={run_id}] Case {i + 1} failed: {exc}")

        run_repo.record_conversation(
            run_id=run_id,
            conversation_run_id=conversation_run_id or f"failed-{i}",
            failed=failed,
        )


# ── Tasks ─────────────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="jobs.run_suite",
    max_retries=0,
)
def run_suite(self, run_id: str, suite_id: str, account_id: str, model: str):
    """Execute all test cases in a suite."""
    run_repo = _runs()
    try:
        cases = _test_cases().get_by_suite(suite_id, account_id)
        if not cases:
            run_repo.mark_failed(run_id, "Suite has no test cases")
            return

        _execute_cases(run_id, account_id, model, cases)
        run_repo.mark_completed(run_id)

    except Exception as exc:
        error_msg = f"{exc}\n{traceback.format_exc()}"
        logger.error(f"[run={run_id}] Suite task failed: {exc}")
        run_repo.mark_failed(run_id, error_msg)
        raise


@celery_app.task(
    bind=True,
    name="jobs.run_case",
    max_retries=0,
)
def run_case(self, run_id: str, case_id: str, account_id: str, model: str):
    """Execute a single test case."""
    run_repo = _runs()
    try:
        case = _test_cases().get(case_id, account_id)
        if not case:
            run_repo.mark_failed(run_id, f"Case {case_id} not found")
            return

        _execute_cases(run_id, account_id, model, [case])
        run_repo.mark_completed(run_id)

    except Exception as exc:
        error_msg = f"{exc}\n{traceback.format_exc()}"
        logger.error(f"[run={run_id}] Case task failed: {exc}")
        run_repo.mark_failed(run_id, error_msg)
        raise
