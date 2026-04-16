from pymongo.collection import Collection
from db.repositories.base import BaseMongoRepository


class InsightRepository(BaseMongoRepository):
    def __init__(self, collection: Collection):
        super().__init__(collection)

    def setup_indexes(self):
        self.collection.create_index("session_id")
        self.collection.create_index("run_id")
        self.collection.create_index("account_id")

    def add(
        self,
        session_id: str,
        analysis: str,
        complete: bool = False,
        run_id: str = None,
        account_id: str = "default",
    ) -> str:
        now = self._now()
        doc = {
            "session_id": session_id,
            "run_id": run_id,
            "analysis": analysis,
            "complete": complete,
            "account_id": account_id,
            "created_at": now,
            "updated_at": now,
        }
        result = self.collection.insert_one(doc)
        return str(result.inserted_id)

    def get(self, insight_id) -> dict | None:
        doc = self.collection.find_one({"_id": self._to_object_id(insight_id)})
        return self._row_to_insight(doc)

    def get_by_session(self, session_id: str, account_id: str = None) -> dict | None:
        query = {"session_id": session_id}
        if account_id:
            query["account_id"] = account_id
        doc = self.collection.find_one(query, sort=[("created_at", -1)])
        return self._row_to_insight(doc)

    def get_all_by_session(self, session_id: str, account_id: str = None) -> list[dict]:
        query = {"session_id": session_id}
        if account_id:
            query["account_id"] = account_id
        docs = self.collection.find(query).sort("created_at", 1)
        return [self._row_to_insight(d) for d in docs]

    def exists_by_run_id(self, run_id: str, account_id: str = None) -> bool:
        query = {"run_id": run_id}
        if account_id:
            query["account_id"] = account_id
        return self.collection.count_documents(query, limit=1) > 0

    def update(self, insight_id, **fields) -> None:
        allowed = {"analysis", "complete", "run_id"}
        to_update = {k: v for k, v in fields.items() if k in allowed}
        if not to_update:
            return
        to_update["updated_at"] = self._now()
        self.collection.update_one(
            {"_id": self._to_object_id(insight_id)},
            {"$set": to_update},
        )

    def get_by_run_id(self, run_id: str, account_id: str = None) -> dict:
        query = {"run_id": run_id}
        if account_id:
            query["account_id"] = account_id
        doc = self.collection.find_one(query, sort=[("created_at", -1)])
        return self._row_to_insight(doc)

    def delete(self, insight_id) -> None:
        self.collection.delete_one({"_id": self._to_object_id(insight_id)})

    def _row_to_insight(self, doc) -> dict | None:
        if doc is None:
            return None
        result = self._serialize(doc)
        result["complete"] = bool(result.get("complete", False))
        return result
