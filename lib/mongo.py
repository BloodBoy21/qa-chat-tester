from pymongo import MongoClient
import os
import certifi
from dotenv import load_dotenv

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB: str = os.getenv("MONGO_DB", "qa_chat_tester")


client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client[MONGO_DB]
