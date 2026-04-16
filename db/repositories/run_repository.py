import time
from datetime import datetime, timezone
from pymongo.collection import Collection
from db.repositories.base import BaseMongoRepository


class RunRepository(BaseMongoRepository):
    """
    Tracks a high-level execution: running a test suite or a set of cases.
    Each Run contains N conversations, each with its own conversation_run_id.
    """

    STATUS_PENDING   = "pending"
    STATUS_RUNNING   = "running"
    STATUS_PAUSED    = "paused"
    STATUS_STOPPED   = "stopped"   # user-initiated stop (distinct from "failed")
    STATUS_COMPLETED = "completed"
    STATUS_FAILED    = "failed"

    # Statuses that allow control actions
    CONTROLLABLE = {STATUS_RUNNING, STATUS_PAUSED, STATUS_PENDING}

    def __init__(self, collection: Collection):
        super().__init__(collection)

    def setup_indexes(self):
        self.collection.create_index("account_id")
        self.collection.create_index("run_id", unique=True)
        self.collection.create_index([("account_id", 1), ("created_at", -1)])
        self.collection.create_index("suite_id")

    def create(
        self,
        run_id: str,
        account_id: str,
        run_type: str,        # "suite" | "case" | "selection"
        total_cases: int,
        model: str,
        suite_id: str = None,
        case_id: str = None,
        case_ids: list[str] = None,   # specific cases selected by the user
    ) -> dict:
        now = self._now_datetime()
        doc = {
            "run_id": run_id,
            "account_id": account_id,
            "type": run_type,
            "suite_id": suite_id,
            "case_id": case_id,
            "case_ids": case_ids,         # None = all cases in suite
            "status": self.STATUS_PENDING,
            "model": model,
            "total_cases": total_cases,
            "completed_cases": 0,
            "failed_cases": 0,
            "conversation_run_ids": [],
            "error": None,
            "created_at": now,
            "started_at": None,
            "finished_at": None,
        }
        self.collection.insert_one(doc)
        doc["_id"] = str(doc["_id"])
        return doc

    def get(self, run_id: str, account_id: str) -> dict | None:
        doc = self.collection.find_one({"run_id": run_id, "account_id": account_id})
        return self._serialize(doc)

    def get_status(self, run_id: str) -> str | None:
        doc = self.collection.find_one({"run_id": run_id}, projection={"status": 1})
        return doc["status"] if doc else None

    def get_all(self, account_id: str, limit: int = 50, suite_id: str = None) -> list[dict]:
        query = {"account_id": account_id}
        if suite_id:
            query["suite_id"] = suite_id
        docs = self.collection.find(query).sort("created_at", -1).limit(limit)
        return [self._serialize(d) for d in docs]

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def mark_running(self, run_id: str) -> None:
        self.collection.update_one(
            {"run_id": run_id},
            {"$set": {"status": self.STATUS_RUNNING, "started_at": self._now_datetime()}},
        )

    def mark_paused(self, run_id: str) -> None:
        self.collection.update_one(
            {"run_id": run_id},
            {"$set": {"status": self.STATUS_PAUSED}},
        )

    def mark_resumed(self, run_id: str) -> None:
        self.collection.update_one(
            {"run_id": run_id},
            {"$set": {"status": self.STATUS_RUNNING}},
        )

    def mark_stopped(self, run_id: str) -> None:
        self.collection.update_one(
            {"run_id": run_id},
            {"$set": {"status": self.STATUS_STOPPED, "finished_at": self._now_datetime()}},
        )

    def mark_completed(self, run_id: str) -> None:
        self.collection.update_one(
            {"run_id": run_id},
            {"$set": {"status": self.STATUS_COMPLETED, "finished_at": self._now_datetime()}},
        )

    def mark_failed(self, run_id: str, error: str) -> None:
        self.collection.update_one(
            {"run_id": run_id},
            {"$set": {
                "status": self.STATUS_FAILED,
                "finished_at": self._now_datetime(),
                "error": error,
            }},
        )

    def record_conversation(self, run_id: str, conversation_run_id: str, failed: bool = False) -> None:
        inc = {"completed_cases": 1}
        if failed:
            inc["failed_cases"] = 1
        self.collection.update_one(
            {"run_id": run_id},
            {
                "$inc": inc,
                "$push": {"conversation_run_ids": conversation_run_id},
            },
        )

    # ── pause/stop helpers used by the Celery task ────────────────────────────

    def wait_if_paused(self, run_id: str, poll_interval: float = 3.0) -> bool:
        """
        Block until the run is no longer paused.
        Returns True if execution should continue, False if it was stopped.
        """
        while True:
            status = self.get_status(run_id)
            if status == self.STATUS_STOPPED:
                return False
            if status != self.STATUS_PAUSED:
                return True
            time.sleep(poll_interval)
