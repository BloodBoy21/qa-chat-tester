"""
LogDB — backward-compatible facade backed by MongoDB.

All existing call-sites (main.py, tools/common.py, etc.) continue to work
without any changes.  Internally, every operation delegates to the typed
repository classes in db/repositories/.

For new code, import the repositories directly:

    from db.repositories import LogRepository, InsightRepository, ...
"""

import os
import threading

from lib.mongo import db as _mongo_db
from db.repositories.log_repository import LogRepository
from db.repositories.case_repository import CaseRepository
from db.repositories.insight_repository import InsightRepository

_DEFAULT_ACCOUNT_ID = os.getenv("DEFAULT_ACCOUNT_ID", "default")


class LogDB:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_repos()
        return cls._instance

    def _init_repos(self):
        self._logs = LogRepository(_mongo_db["logs"])
        self._cases = CaseRepository(_mongo_db["cases"])
        self._insights = InsightRepository(_mongo_db["insights"])

    # ── logs ──────────────────────────────────────────────────────────────────

    def add(
        self,
        message,
        response,
        raw_response,
        user_id,
        session_id,
        files=None,
        images=None,
        campaigns=None,
        run_id=None,
        scenario_group_id=None,
        scenario=None,
        account_id=None,
    ):
        return self._logs.add(
            message=message,
            response=response,
            raw_response=raw_response,
            user_id=user_id,
            session_id=session_id,
            account_id=account_id or _DEFAULT_ACCOUNT_ID,
            files=files,
            images=images,
            campaigns=campaigns,
            run_id=run_id,
            scenario_group_id=scenario_group_id,
            scenario=scenario,
        )

    def get(self, log_id):
        return self._logs.get(log_id)

    def get_by_session(self, session_id, run_id=None):
        return self._logs.get_by_session(session_id, run_id=run_id)

    def get_by_run_id(self, run_id):
        return self._logs.get_by_run_id(run_id)

    def get_by_user(self, user_id, limit=50):
        return self._logs.get_by_user(user_id, limit=limit)

    def update(self, log_id, **fields):
        return self._logs.update(log_id, **fields)

    def delete(self, log_id):
        return self._logs.delete(log_id)

    # ── cases ─────────────────────────────────────────────────────────────────

    def add_case(self, run_id, payload, account_id=None):
        return self._cases.add(
            run_id=run_id,
            payload=payload,
            account_id=account_id or _DEFAULT_ACCOUNT_ID,
        )

    def get_case(self, case_id):
        return self._cases.get(case_id)

    def get_cases_by_run_id(self, run_id):
        return self._cases.get_by_run_id(run_id)

    def exits_case_for_run_id(self, run_id):
        return self._cases.exists_for_run_id(run_id)

    def update_case(self, case_id, **fields):
        return self._cases.update(case_id, **fields)

    def delete_case(self, case_id):
        return self._cases.delete(case_id)

    # ── insights ──────────────────────────────────────────────────────────────

    def add_insight(self, session_id, analysis, complete=False, run_id=None, account_id=None):
        return self._insights.add(
            session_id=session_id,
            analysis=analysis,
            complete=complete,
            run_id=run_id,
            account_id=account_id or _DEFAULT_ACCOUNT_ID,
        )

    def get_insight(self, insight_id):
        return self._insights.get(insight_id)

    def get_insight_by_session(self, session_id):
        return self._insights.get_by_session(session_id)

    def get_insights_by_session(self, session_id):
        return self._insights.get_all_by_session(session_id)

    def update_insight(self, insight_id, **fields):
        return self._insights.update(insight_id, **fields)

    def delete_insight(self, insight_id):
        return self._insights.delete(insight_id)

    def insight_exists_by_run_id(self, run_id):
        return self._insights.exists_by_run_id(run_id)

    def get_session_id_by_run_id(self, run_id):
        return self._logs.get_session_id_by_run_id(run_id)

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def close(self):
        # MongoDB connection lifecycle is handled globally in lib/mongo.py
        LogDB._instance = None
