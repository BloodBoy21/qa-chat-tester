import sqlite3
import json
from datetime import datetime, timezone


class LogDB:
    _instance = None

    def __new__(cls, db_path="logs.db"):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._conn = sqlite3.connect(db_path)
            cls._instance._conn.row_factory = sqlite3.Row
            cls._instance._create_tables()
        return cls._instance

    def _create_tables(self):
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS logs (
                log_id       INTEGER PRIMARY KEY AUTOINCREMENT,
                message      TEXT,
                response     TEXT,
                raw_response TEXT,
                user_id      TEXT,
                session_id   TEXT,
                created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                updated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            );

            CREATE TRIGGER IF NOT EXISTS logs_updated_at
            AFTER UPDATE ON logs
            BEGIN
                UPDATE logs SET updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                WHERE log_id = NEW.log_id;
            END;
        """
        )

    def _now(self):
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def add(self, message, response, raw_response, user_id, session_id):
        now = self._now()
        cursor = self._conn.execute(
            """
            INSERT INTO logs (message, response, raw_response, user_id, session_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message,
                response,
                json.dumps(raw_response),
                user_id,
                session_id,
                now,
                now,
            ),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get(self, log_id):
        row = self._conn.execute(
            "SELECT * FROM logs WHERE log_id = ?", (log_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_by_session(self, session_id):
        rows = self._conn.execute(
            "SELECT * FROM logs WHERE session_id = ? ORDER BY created_at", (session_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_by_user(self, user_id, limit=50):
        rows = self._conn.execute(
            "SELECT * FROM logs WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def update(self, log_id, **fields):
        allowed = {"message", "response", "raw_response", "user_id", "session_id"}
        to_update = {k: v for k, v in fields.items() if k in allowed}
        if not to_update:
            return
        if "raw_response" in to_update:
            to_update["raw_response"] = json.dumps(to_update["raw_response"])
        sets = ", ".join(f"{k} = ?" for k in to_update)
        vals = list(to_update.values()) + [log_id]
        self._conn.execute(f"UPDATE logs SET {sets} WHERE log_id = ?", vals)
        self._conn.commit()

    def delete(self, log_id):
        self._conn.execute("DELETE FROM logs WHERE log_id = ?", (log_id,))
        self._conn.commit()

    def close(self):
        self._conn.close()
        LogDB._instance = None
