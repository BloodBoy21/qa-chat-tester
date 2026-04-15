from pymongo.collection import Collection
from db.repositories.base import BaseMongoRepository


class TestSuiteRepository(BaseMongoRepository):
    def __init__(self, collection: Collection):
        super().__init__(collection)

    def setup_indexes(self):
        self.collection.create_index("account_id")
        self.collection.create_index([("account_id", 1), ("created_at", -1)])

    def create(self, account_id: str, title: str, description: str = None) -> dict:
        now = self._now_datetime()
        doc = {
            "account_id": account_id,
            "title": title,
            "description": description,
            "created_at": now,
            "updated_at": now,
        }
        result = self.collection.insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        return doc

    def get(self, suite_id, account_id: str) -> dict | None:
        doc = self.collection.find_one({
            "_id": self._to_object_id(suite_id),
            "account_id": account_id,
        })
        return self._serialize(doc)

    def get_all(self, account_id: str) -> list[dict]:
        docs = self.collection.find(
            {"account_id": account_id},
            sort=[("created_at", -1)],
        )
        return [self._serialize(d) for d in docs]

    def update(self, suite_id, account_id: str, **fields) -> dict | None:
        allowed = {"title", "description"}
        to_update = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not to_update:
            return self.get(suite_id, account_id)
        to_update["updated_at"] = self._now_datetime()
        doc = self.collection.find_one_and_update(
            {"_id": self._to_object_id(suite_id), "account_id": account_id},
            {"$set": to_update},
            return_document=True,
        )
        return self._serialize(doc)

    def delete(self, suite_id, account_id: str) -> bool:
        result = self.collection.delete_one({
            "_id": self._to_object_id(suite_id),
            "account_id": account_id,
        })
        return result.deleted_count > 0

    def exists(self, suite_id, account_id: str) -> bool:
        return self.collection.count_documents(
            {"_id": self._to_object_id(suite_id), "account_id": account_id},
            limit=1,
        ) > 0
