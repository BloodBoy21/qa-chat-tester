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
                files        TEXT,
                images       TEXT,
                user_id      TEXT,
                session_id   TEXT,
                run_id       TEXT,
                created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                updated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            );
            CREATE TRIGGER IF NOT EXISTS logs_updated_at
            AFTER UPDATE ON logs
            BEGIN
                UPDATE logs SET updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                WHERE log_id = NEW.log_id;
            END;

            CREATE TABLE IF NOT EXISTS insights (
                insight_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id   TEXT NOT NULL,
                run_id       TEXT,
                analysis     TEXT,
                complete     INTEGER NOT NULL DEFAULT 0,
                created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                updated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            );
            CREATE TRIGGER IF NOT EXISTS insights_updated_at
            AFTER UPDATE ON insights
            BEGIN
                UPDATE insights SET updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                WHERE insight_id = NEW.insight_id;
            END;
        """
        )

    def _now(self):
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── logs ──

    def add(
        self,
        message,
        response,
        raw_response,
        user_id,
        session_id,
        files=None,
        images=None,
        run_id=None,
    ):
        now = self._now()
        cursor = self._conn.execute(
            """
            INSERT INTO logs (message, response, raw_response, files, images, user_id, session_id, run_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message,
                response,
                json.dumps(raw_response),
                json.dumps(files) if files is not None else None,
                json.dumps(images) if images is not None else None,
                user_id,
                session_id,
                run_id,
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

    def get_by_session(self, session_id, run_id=None):
        if run_id:
            rows = self._conn.execute(
                "SELECT * FROM logs WHERE session_id = ? AND run_id = ? ORDER BY created_at",
                (session_id, run_id),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM logs WHERE session_id = ? ORDER BY created_at",
                (session_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_by_user(self, user_id, limit=50):
        rows = self._conn.execute(
            "SELECT * FROM logs WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def update(self, log_id, **fields):
        allowed = {
            "message",
            "response",
            "raw_response",
            "files",
            "images",
            "user_id",
            "session_id",
            "run_id",
        }
        to_update = {k: v for k, v in fields.items() if k in allowed}
        if not to_update:
            return
        for json_field in ("raw_response", "files", "images"):
            if json_field in to_update and to_update[json_field] is not None:
                to_update[json_field] = json.dumps(to_update[json_field])
        sets = ", ".join(f"{k} = ?" for k in to_update)
        vals = list(to_update.values()) + [log_id]
        self._conn.execute(f"UPDATE logs SET {sets} WHERE log_id = ?", vals)
        self._conn.commit()

    def delete(self, log_id):
        self._conn.execute("DELETE FROM logs WHERE log_id = ?", (log_id,))
        self._conn.commit()

    # ── insights ──

    def add_insight(self, session_id, analysis, complete=False, run_id=None):
        now = self._now()
        cursor = self._conn.execute(
            """
            INSERT INTO insights (session_id, run_id, analysis, complete, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, run_id, analysis, 1 if complete else 0, now, now),
        )
        self._conn.commit()
        return cursor.lastrowid

    def _row_to_insight(self, row):
        if not row:
            return None
        data = dict(row)
        data["complete"] = bool(data["complete"])
        return data

    def get_insight(self, insight_id):
        row = self._conn.execute(
            "SELECT * FROM insights WHERE insight_id = ?", (insight_id,)
        ).fetchone()
        return self._row_to_insight(row)

    def get_insight_by_session(self, session_id):
        row = self._conn.execute(
            "SELECT * FROM insights WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        return self._row_to_insight(row)

    def get_insights_by_session(self, session_id):
        rows = self._conn.execute(
            "SELECT * FROM insights WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        ).fetchall()
        return [self._row_to_insight(r) for r in rows]

    def update_insight(self, insight_id, **fields):
        allowed = {"analysis", "complete", "run_id"}
        to_update = {k: v for k, v in fields.items() if k in allowed}
        if not to_update:
            return
        if "complete" in to_update:
            to_update["complete"] = 1 if to_update["complete"] else 0
        sets = ", ".join(f"{k} = ?" for k in to_update)
        vals = list(to_update.values()) + [insight_id]
        self._conn.execute(f"UPDATE insights SET {sets} WHERE insight_id = ?", vals)
        self._conn.commit()

    def delete_insight(self, insight_id):
        self._conn.execute("DELETE FROM insights WHERE insight_id = ?", (insight_id,))
        self._conn.commit()

    def insight_exists_by_run_id(self, run_id):
        row = self._conn.execute(
            "SELECT 1 FROM insights WHERE run_id = ? LIMIT 1", (run_id,)
        ).fetchone()
        return row is not None

    def get_session_id_by_run_id(self, run_id):
        row = self._conn.execute(
            "SELECT session_id FROM logs WHERE run_id = ? ORDER BY created_at DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        return row["session_id"] if row else None

    # ── lifecycle ──

    def close(self):
        self._conn.close()
        LogDB._instance = None
