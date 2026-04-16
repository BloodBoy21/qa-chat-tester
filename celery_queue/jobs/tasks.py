"""
Celery tasks for running test suites and individual test cases.

Lifecycle per task:
  1. Marks the Run as "running" in MongoDB
  2. Iterates over the test case payloads
  3. Between each case: checks for pause (waits) or stop (exits early)
  4. Calls run_agent() from lib/agent_loop for each case
  5. Records every conversation run_id produced
  6. Marks the Run as completed / stopped / failed
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
from lib.agent_loop import run_agent


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
) -> str:
    """
    Core loop: run each case through run_agent and track results in the Run doc.
    Returns the final status string ("completed" | "stopped").
    Runs inside a Celery worker process (sync context).
    """
    run_repo = _runs()
    run_repo.mark_running(run_id)

    for i, case in enumerate(cases):
        # ── pause / stop check ────────────────────────────────────────────────
        should_continue = run_repo.wait_if_paused(run_id)
        if not should_continue:
            logger.info(f"[run={run_id}] Stopped by user before case {i + 1}")
            return RunRepository.STATUS_STOPPED

        payload = case.get("payload", case)
        user_id = (
            payload.get("user_id", "default_user")
            if isinstance(payload, dict)
            else "default_user"
        )
        context = (
            payload if isinstance(payload, str) else __import__("json").dumps(payload)
        )

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

    return RunRepository.STATUS_COMPLETED


# ── Tasks ─────────────────────────────────────────────────────────────────────

@celery_app.task(bind=True, name="jobs.run_suite", max_retries=0)
def run_suite(
    self,
    run_id: str,
    suite_id: str,
    account_id: str,
    model: str,
    case_ids: list[str] | None = None,
):
    """
    Execute test cases in a suite.
    If case_ids is provided, only those cases are run (in suite order).
    """
    run_repo = _runs()
    try:
        all_cases = _test_cases().get_by_suite(suite_id, account_id)

        if case_ids:
            id_set = set(case_ids)
            cases = [c for c in all_cases if c["_id"] in id_set]
        else:
            cases = all_cases

        if not cases:
            run_repo.mark_failed(run_id, "No cases to execute")
            return

        final_status = _execute_cases(run_id, account_id, model, cases)

        if final_status == RunRepository.STATUS_STOPPED:
            run_repo.mark_stopped(run_id)
        else:
            run_repo.mark_completed(run_id)

    except Exception as exc:
        error_msg = f"{exc}\n{traceback.format_exc()}"
        logger.error(f"[run={run_id}] Suite task failed: {exc}")
        run_repo.mark_failed(run_id, error_msg)
        raise


@celery_app.task(bind=True, name="jobs.run_case", max_retries=0)
def run_case(self, run_id: str, case_id: str, account_id: str, model: str):
    """Execute a single test case."""
    run_repo = _runs()
    try:
        case = _test_cases().get(case_id, account_id)
        if not case:
            run_repo.mark_failed(run_id, f"Case {case_id} not found")
            return

        final_status = _execute_cases(run_id, account_id, model, [case])

        if final_status == RunRepository.STATUS_STOPPED:
            run_repo.mark_stopped(run_id)
        else:
            run_repo.mark_completed(run_id)

    except Exception as exc:
        error_msg = f"{exc}\n{traceback.format_exc()}"
        logger.error(f"[run={run_id}] Case task failed: {exc}")
        run_repo.mark_failed(run_id, error_msg)
        raise
