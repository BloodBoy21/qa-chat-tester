import json
from pymongo.collection import Collection
from db.repositories.base import BaseMongoRepository


class TestCaseRepository(BaseMongoRepository):
    def __init__(self, collection: Collection):
        super().__init__(collection)

    def setup_indexes(self):
        self.collection.create_index("account_id")
        self.collection.create_index("suite_id")
        self.collection.create_index([("account_id", 1), ("suite_id", 1)])
        self.collection.create_index([("account_id", 1), ("suite_id", 1), ("created_at", 1)])

    # ── single case ───────────────────────────────────────────────────────────

    def create(
        self,
        account_id: str,
        suite_id: str,
        title: str,
        payload: dict,
        description: str = None,
    ) -> dict:
        now = self._now_datetime()
        doc = {
            "account_id": account_id,
            "suite_id": suite_id,
            "title": title,
            "description": description,
            "payload": payload,
            "created_at": now,
            "updated_at": now,
        }
        result = self.collection.insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        return doc

    def get(self, case_id, account_id: str) -> dict | None:
        doc = self.collection.find_one({
            "_id": self._to_object_id(case_id),
            "account_id": account_id,
        })
        return self._serialize(doc)

    def update(self, case_id, account_id: str, **fields) -> dict | None:
        allowed = {"title", "description", "payload"}
        to_update = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not to_update:
            return self.get(case_id, account_id)
        to_update["updated_at"] = self._now_datetime()
        doc = self.collection.find_one_and_update(
            {"_id": self._to_object_id(case_id), "account_id": account_id},
            {"$set": to_update},
            return_document=True,
        )
        return self._serialize(doc)

    def delete(self, case_id, account_id: str) -> bool:
        result = self.collection.delete_one({
            "_id": self._to_object_id(case_id),
            "account_id": account_id,
        })
        return result.deleted_count > 0

    # ── suite-scoped queries ───────────────────────────────────────────────────

    def get_by_suite(self, suite_id: str, account_id: str) -> list[dict]:
        docs = self.collection.find(
            {"suite_id": suite_id, "account_id": account_id},
            sort=[("created_at", 1)],
        )
        return [self._serialize(d) for d in docs]

    def count_by_suite(self, suite_id: str, account_id: str) -> int:
        return self.collection.count_documents(
            {"suite_id": suite_id, "account_id": account_id}
        )

    def delete_by_suite(self, suite_id: str, account_id: str) -> int:
        result = self.collection.delete_many(
            {"suite_id": suite_id, "account_id": account_id}
        )
        return result.deleted_count

    # ── bulk upload ────────────────────────────────────────────────────────────

    def bulk_create(
        self,
        account_id: str,
        suite_id: str,
        items: list[dict],
        replace: bool = True,
    ) -> int:
        """
        Each item in `items` must have at least a `payload` key.
        Optional keys: `title`, `description`.
        If replace=True, all existing cases in the suite are deleted first.
        """
        if replace:
            self.delete_by_suite(suite_id, account_id)
        if not items:
            return 0
        now = self._now_datetime()
        docs = [
            {
                "account_id": account_id,
                "suite_id": suite_id,
                "title": item.get("title", f"Case {i + 1}"),
                "description": item.get("description"),
                "payload": item.get("payload", item),  # fallback: whole item is the payload
                "created_at": now,
                "updated_at": now,
            }
            for i, item in enumerate(items)
        ]
        result = self.collection.insert_many(docs)
        return len(result.inserted_ids)
