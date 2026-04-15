from datetime import datetime, timezone
from bson import ObjectId
from pymongo.collection import Collection


class BaseMongoRepository:
    def __init__(self, collection: Collection):
        self.collection = collection

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _serialize(doc: dict | None) -> dict | None:
        if doc is None:
            return None
        result = dict(doc)
        if "_id" in result:
            result["_id"] = str(result["_id"])
        return result

    @staticmethod
    def _to_object_id(id_val):
        if isinstance(id_val, ObjectId):
            return id_val
        try:
            return ObjectId(str(id_val))
        except Exception:
            return id_val
