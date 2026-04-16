"""
Celery tasks — high-throughput parallel execution.

Architecture
────────────
run_suite / run_case
  └─ Dispatches N individual process_case tasks via celery.group
      └─ Each process_case runs ONE conversation in its own worker slot
         └─ After finishing, atomically tries to mark the run complete

This allows 40-100+ simultaneous conversations depending on worker count
and concurrency setting.

Pause / Stop
────────────
Each process_case checks the run status before starting the conversation.
If paused  → waits (polling MongoDB) until resumed or stopped.
If stopped → exits immediately without running the conversation.
"""

from __future__ import annotations

import asyncio
import json
import traceback

from dotenv import load_dotenv

load_dotenv()

from celery import group
from celery.exceptions import SoftTimeLimitExceeded
from loguru import logger

from celery_queue.config import celery_app
from lib.mongo import db
from db.repositories.test_case_repository import TestCaseRepository
from db.repositories.run_repository import RunRepository
from lib.agent_loop import run_agent


# ── Repo helpers ──────────────────────────────────────────────────────────────

def _runs() -> RunRepository:
    return RunRepository(db["runs"])


def _test_cases() -> TestCaseRepository:
    return TestCaseRepository(db["test_cases"])


# ── Core single-case task ─────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="jobs.process_case",
    max_retries=3,
    # Retry on Gemini 429 / quota errors — back off 60 s between retries
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    retry_backoff=True,
    retry_backoff_max=120,
    dont_autoretry_for=(SoftTimeLimitExceeded,),
)
def process_case(
    self,
    run_id: str,
    case_id: str,
    account_id: str,
    model: str,
    index: int,
    total: int,
):
    """
    Execute a single test case (one full conversation + analysis).
    Runs inside its own worker slot — completely independent of other cases.
    """
    run_repo = _runs()

    # ── Pause / stop check before starting ────────────────────────────────────
    should_continue = run_repo.wait_if_paused(run_id)
    if not should_continue:
        logger.info(f"[run={run_id}] Case {index+1}/{total} skipped (run stopped)")
        # Still count it so try_complete works correctly
        run_repo.record_conversation(
            run_id=run_id,
            conversation_run_id=f"skipped-{index}",
            failed=False,
        )
        run_repo.try_complete(run_id)
        return {"skipped": True}

    # ── Fetch case from MongoDB ────────────────────────────────────────────────
    case = _test_cases().get(case_id, account_id)
    if not case:
        logger.error(f"[run={run_id}] Case {case_id} not found, skipping")
        run_repo.record_conversation(
            run_id=run_id,
            conversation_run_id=f"not-found-{index}",
            failed=True,
        )
        run_repo.try_complete(run_id)
        return {"skipped": True}

    payload = case.get("payload", case)
    user_id = (
        payload.get("user_id", "default_user")
        if isinstance(payload, dict)
        else "default_user"
    )
    context = payload if isinstance(payload, str) else json.dumps(payload)

    logger.info(f"[run={run_id}] Starting case {index+1}/{total} | user_id={user_id}")

    # ── Run the conversation ───────────────────────────────────────────────────
    conversation_run_id = None
    failed = False
    try:
        conversation_run_id = asyncio.run(
            run_agent(
                context=context,
                user_id=user_id,
                model=model,
                item_index=index,
                total_items=total,
                account_id=account_id,
            )
        )
        logger.info(f"[run={run_id}] Case {index+1}/{total} done | conv={conversation_run_id}")

    except SoftTimeLimitExceeded:
        failed = True
        logger.error(f"[run={run_id}] Case {index+1}/{total} timed out (soft limit)")
        # Don't retry on timeout — just mark as failed and move on
        raise

    except Exception as exc:
        failed = True
        err = str(exc)
        logger.error(f"[run={run_id}] Case {index+1}/{total} failed: {err}")

        # Only retry on rate-limit / quota errors
        is_rate_limit = any(k in err.lower() for k in ("429", "quota", "rate limit", "resource exhausted"))
        if not is_rate_limit:
            self.max_retries = 0   # skip retries for non-rate-limit failures

        raise  # celery handles autoretry

    finally:
        # Always record the attempt, even on failure
        run_repo.record_conversation(
            run_id=run_id,
            conversation_run_id=conversation_run_id or f"failed-{index}",
            failed=failed,
        )
        # Try to close out the run if this was the last case
        run_repo.try_complete(run_id)

    return {
        "conversation_run_id": conversation_run_id,
        "failed": failed,
        "index": index,
    }


# ── Suite orchestrator (dispatches parallel tasks) ────────────────────────────

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
    Dispatch all suite cases as parallel process_case tasks.
    Returns immediately after dispatch — does NOT wait for cases to finish.
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

        run_repo.mark_running(run_id)
        logger.info(f"[run={run_id}] Dispatching {len(cases)} cases in parallel")

        # Dispatch all cases as independent parallel tasks
        task_group = group(
            process_case.s(
                run_id=run_id,
                case_id=c["_id"],
                account_id=account_id,
                model=model,
                index=i,
                total=len(cases),
            )
            for i, c in enumerate(cases)
        )
        task_group.apply_async()

    except Exception as exc:
        error_msg = f"{exc}\n{traceback.format_exc()}"
        logger.error(f"[run={run_id}] Suite dispatch failed: {exc}")
        run_repo.mark_failed(run_id, error_msg)
        raise


# ── Single-case runner (from API trigger) ─────────────────────────────────────

@celery_app.task(bind=True, name="jobs.run_case", max_retries=0)
def run_case(self, run_id: str, case_id: str, account_id: str, model: str):
    """Run a single case (triggers process_case directly)."""
    run_repo = _runs()
    try:
        case = _test_cases().get(case_id, account_id)
        if not case:
            run_repo.mark_failed(run_id, f"Case {case_id} not found")
            return

        run_repo.mark_running(run_id)

        # Delegate to process_case (inline, not async dispatch)
        process_case(
            run_id=run_id,
            case_id=case_id,
            account_id=account_id,
            model=model,
            index=0,
            total=1,
        )

    except Exception as exc:
        error_msg = f"{exc}\n{traceback.format_exc()}"
        logger.error(f"[run={run_id}] Single case failed: {exc}")
        run_repo.mark_failed(run_id, error_msg)
        raise
