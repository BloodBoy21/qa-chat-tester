from pymongo.collection import Collection
from db.repositories.base import BaseMongoRepository


class ConversationRepository(BaseMongoRepository):
    """
    A conversation groups all logs under the same session_id for a given tenant.
    It is created/updated automatically when a session produces log entries.
    """

    def __init__(self, collection: Collection):
        super().__init__(collection)

    def setup_indexes(self):
        self.collection.create_index(
            [("account_id", 1), ("session_id", 1)], unique=True
        )
        self.collection.create_index("account_id")
        self.collection.create_index("user_id")
        self.collection.create_index("created_at")

    def create_or_update(
        self,
        account_id: str,
        user_id: str,
        run_id: str = None,
    ) -> str:
        now = self._now()
        update: dict = {
            "$setOnInsert": {
                "account_id": account_id,
                "user_id": user_id,
                "created_at": now,
            },
            "$set": {"updated_at": now},
        }
        if run_id:
            update["$addToSet"] = {"run_ids": run_id}

        result = self.collection.update_one(
            {"account_id": account_id},
            update,
            upsert=True,
        )
        if result.upserted_id:
            return str(result.upserted_id)
        doc = self.collection.find_one(
            {"account_id": account_id},
            projection={"_id": 1},
        )
        return str(doc["_id"]) if doc else None

    def get_by_session(self, session_id: str, account_id: str) -> dict | None:
        doc = self.collection.find_one(
            {"session_id": session_id, "account_id": account_id}
        )
        return self._serialize(doc)

    def get_by_account(
        self, account_id: str, limit: int = 50, skip: int = 0
    ) -> list[dict]:
        docs = (
            self.collection.find({"account_id": account_id})
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        return [self._serialize(d) for d in docs]

    def get_by_user(self, user_id: str, account_id: str, limit: int = 50) -> list[dict]:
        docs = (
            self.collection.find({"user_id": user_id, "account_id": account_id})
            .sort("created_at", -1)
            .limit(limit)
        )
        return [self._serialize(d) for d in docs]

    def get_by_run_id(self, run_id: str) -> list[dict]:
        docs = self.collection.find({"run_ids": run_id}).sort("created_at", -1)
        return [self._serialize(d) for d in docs]

    def delete(self, session_id: str, account_id: str) -> None:
        self.collection.delete_one({"session_id": session_id, "account_id": account_id})
