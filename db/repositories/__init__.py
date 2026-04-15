from db.repositories.log_repository import LogRepository
from db.repositories.case_repository import CaseRepository
from db.repositories.insight_repository import InsightRepository
from db.repositories.account_repository import AccountRepository
from db.repositories.conversation_repository import ConversationRepository
from db.repositories.test_case_repository import TestCaseRepository
from db.repositories.test_suite_repository import TestSuiteRepository
from db.repositories.user_repository import UserRepository

__all__ = [
    "LogRepository",
    "CaseRepository",
    "InsightRepository",
    "AccountRepository",
    "ConversationRepository",
    "TestCaseRepository",
    "TestSuiteRepository",
    "UserRepository",
]


def setup_indexes(mongo_db) -> None:
    """
    Create all MongoDB indexes.
    Call once at application startup after the DB connection is established.
    """
    LogRepository(mongo_db["logs"]).setup_indexes()
    CaseRepository(mongo_db["cases"]).setup_indexes()
    InsightRepository(mongo_db["insights"]).setup_indexes()
    AccountRepository(mongo_db["accounts"]).setup_indexes()
    ConversationRepository(mongo_db["conversations"]).setup_indexes()
    TestSuiteRepository(mongo_db["test_suites"]).setup_indexes()
    TestCaseRepository(mongo_db["test_cases"]).setup_indexes()
