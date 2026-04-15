from pymongo import MongoClient
import os
import certifi
from dotenv import load_dotenv

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB: str = os.getenv("MONGO_DB", "qa_chat_tester")

TSL_CA_FILE = (
    certifi.where() if os.getenv("MONGO_TLS", "false").lower() == "true" else None
)
client = MongoClient(MONGO_URI, tlsCAFile=TSL_CA_FILE)
db = client[MONGO_DB]
