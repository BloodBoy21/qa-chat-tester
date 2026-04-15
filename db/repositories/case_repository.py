import json
from pymongo.collection import Collection
from db.repositories.base import BaseMongoRepository


class CaseRepository(BaseMongoRepository):
    def __init__(self, collection: Collection):
        super().__init__(collection)

    def setup_indexes(self):
        self.collection.create_index("run_id")
        self.collection.create_index("account_id")

    def add(self, run_id: str, payload, account_id: str = "default") -> str:
        now = self._now()
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                pass
        doc = {
            "run_id": run_id,
            "payload": payload,
            "account_id": account_id,
            "created_at": now,
            "updated_at": now,
        }
        result = self.collection.insert_one(doc)
        return str(result.inserted_id)

    def get(self, case_id) -> dict | None:
        doc = self.collection.find_one({"_id": self._to_object_id(case_id)})
        return self._serialize(doc)

    def get_by_run_id(self, run_id: str, account_id: str = None) -> list[dict]:
        query = {"run_id": run_id}
        if account_id:
            query["account_id"] = account_id
        docs = self.collection.find(query).sort("created_at", 1)
        return [self._serialize(d) for d in docs]

    def exists_for_run_id(self, run_id: str, account_id: str = None) -> bool:
        query = {"run_id": run_id}
        if account_id:
            query["account_id"] = account_id
        return self.collection.count_documents(query, limit=1) > 0

    def update(self, case_id, **fields) -> None:
        allowed = {"run_id", "payload"}
        to_update = {k: v for k, v in fields.items() if k in allowed}
        if not to_update:
            return
        if "payload" in to_update and isinstance(to_update["payload"], str):
            try:
                to_update["payload"] = json.loads(to_update["payload"])
            except json.JSONDecodeError:
                pass
        to_update["updated_at"] = self._now()
        self.collection.update_one(
            {"_id": self._to_object_id(case_id)},
            {"$set": to_update},
        )

    def delete(self, case_id) -> None:
        self.collection.delete_one({"_id": self._to_object_id(case_id)})
