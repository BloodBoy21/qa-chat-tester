# Deprecated — use lib/sql_db instead.
# SQLAlchemy auto-selects MySQL or SQLite based on DATABASE_URL.
from lib.sql_db import engine, get_session, init_db  # noqa: F401
