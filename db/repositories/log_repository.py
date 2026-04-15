import json
from pymongo.collection import Collection
from db.repositories.base import BaseMongoRepository


class LogRepository(BaseMongoRepository):
    def __init__(self, collection: Collection):
        super().__init__(collection)

    def setup_indexes(self):
        self.collection.create_index("session_id")
        self.collection.create_index("run_id")
        self.collection.create_index("user_id")
        self.collection.create_index("account_id")
        self.collection.create_index([("account_id", 1), ("session_id", 1)])

    def add(
        self,
        message: str,
        response: str,
        raw_response,
        user_id: str,
        session_id: str,
        account_id: str = "default",
        files=None,
        images=None,
        campaigns=None,
        run_id: str = None,
        scenario_group_id: str = None,
        scenario: str = None,
    ) -> str:
        now = self._now()
        doc = {
            "message": message,
            "response": response,
            "raw_response": raw_response if isinstance(raw_response, str) else json.dumps(raw_response),
            "files": json.dumps(files) if files is not None else None,
            "images": json.dumps(images) if images is not None else None,
            "campaigns": json.dumps(campaigns) if campaigns is not None else None,
            "user_id": user_id,
            "session_id": session_id,
            "account_id": account_id,
            "run_id": run_id,
            "scenario_group_id": scenario_group_id,
            "scenario": scenario,
            "created_at": now,
            "updated_at": now,
        }
        result = self.collection.insert_one(doc)
        return str(result.inserted_id)

    def get(self, log_id) -> dict | None:
        doc = self.collection.find_one({"_id": self._to_object_id(log_id)})
        return self._serialize(doc)

    def get_by_session(
        self,
        session_id: str,
        run_id: str = None,
        account_id: str = None,
    ) -> list[dict]:
        query = {"session_id": session_id}
        if run_id:
            query["run_id"] = run_id
        if account_id:
            query["account_id"] = account_id
        docs = self.collection.find(query).sort("created_at", 1)
        return [self._serialize(d) for d in docs]

    def get_by_run_id(self, run_id: str, account_id: str = None) -> list[dict]:
        query = {"run_id": run_id}
        if account_id:
            query["account_id"] = account_id
        docs = self.collection.find(query).sort("created_at", 1)
        return [self._serialize(d) for d in docs]

    def get_by_user(self, user_id: str, account_id: str = None, limit: int = 50) -> list[dict]:
        query = {"user_id": user_id}
        if account_id:
            query["account_id"] = account_id
        docs = self.collection.find(query).sort("created_at", -1).limit(limit)
        return [self._serialize(d) for d in docs]

    def update(self, log_id, **fields) -> None:
        allowed = {
            "message", "response", "raw_response", "files", "images",
            "campaigns", "user_id", "session_id", "run_id",
            "scenario_group_id", "scenario",
        }
        to_update = {k: v for k, v in fields.items() if k in allowed}
        if not to_update:
            return
        for json_field in ("raw_response", "files", "images", "campaigns"):
            if json_field in to_update and to_update[json_field] is not None:
                if not isinstance(to_update[json_field], str):
                    to_update[json_field] = json.dumps(to_update[json_field])
        to_update["updated_at"] = self._now()
        self.collection.update_one(
            {"_id": self._to_object_id(log_id)},
            {"$set": to_update},
        )

    def delete(self, log_id) -> None:
        self.collection.delete_one({"_id": self._to_object_id(log_id)})

    def get_session_id_by_run_id(self, run_id: str) -> str | None:
        doc = self.collection.find_one(
            {"run_id": run_id},
            sort=[("created_at", -1)],
            projection={"session_id": 1},
        )
        return doc["session_id"] if doc else None
