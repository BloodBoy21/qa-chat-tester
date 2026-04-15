"""
SQL database connection via SQLAlchemy.

Backend is selected automatically from DATABASE_URL:
  - Not set / sqlite:// → SQLite  (default: sqlite:///users.db)
  - mysql+pymysql://…   → MySQL

Usage:
    from lib.sql_db import get_session, init_db

    with get_session() as session:
        session.add(...)

    # At app startup, call once to create tables:
    init_db()
"""

import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///users.db")
_is_sqlite = _DATABASE_URL.startswith("sqlite")


def _build_engine():
    kwargs: dict = {}
    if _is_sqlite:
        # SQLite needs check_same_thread=False to work across threads
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # For MySQL (or any network DB): validate connections before use
        kwargs["pool_pre_ping"] = True
        kwargs["pool_recycle"] = 3600
    return create_engine(_DATABASE_URL, **kwargs)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


@contextmanager
def get_session():
    """Provide a transactional session scope."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """
    Create all SQL tables if they do not exist.
    Must be called at application startup after all models are imported.
    """
    import db.models  # noqa: F401 — registers models with Base.metadata
    Base.metadata.create_all(engine)
