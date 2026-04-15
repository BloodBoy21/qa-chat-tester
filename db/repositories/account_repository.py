from pymongo.collection import Collection
from db.repositories.base import BaseMongoRepository


class AccountRepository(BaseMongoRepository):
    def __init__(self, collection: Collection):
        super().__init__(collection)

    def setup_indexes(self):
        self.collection.create_index("account_id", unique=True)
        self.collection.create_index("name")

    def create(self, account_id: str, name: str, **kwargs) -> str:
        now = self._now()
        doc = {
            "account_id": account_id,
            "name": name,
            "created_at": now,
            "updated_at": now,
            **kwargs,
        }
        result = self.collection.insert_one(doc)
        return str(result.inserted_id)

    def get(self, account_id: str) -> dict | None:
        doc = self.collection.find_one({"account_id": account_id})
        return self._serialize(doc)

    def get_all(self) -> list[dict]:
        docs = self.collection.find().sort("created_at", 1)
        return [self._serialize(d) for d in docs]

    def update(self, account_id: str, **fields) -> None:
        allowed = {"name"}
        to_update = {k: v for k, v in fields.items() if k in allowed}
        if not to_update:
            return
        to_update["updated_at"] = self._now()
        self.collection.update_one(
            {"account_id": account_id},
            {"$set": to_update},
        )

    def delete(self, account_id: str) -> None:
        self.collection.delete_one({"account_id": account_id})

    def exists(self, account_id: str) -> bool:
        return self.collection.count_documents({"account_id": account_id}, limit=1) > 0
