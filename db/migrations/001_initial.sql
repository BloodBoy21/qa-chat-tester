-- ============================================================
-- Migration 001 — Initial schema  (reference / documentation)
-- ============================================================
-- SQLAlchemy generates and runs this schema automatically via
-- lib/sql_db.init_db().  This file is kept as human-readable
-- documentation and can be run manually if needed.
--
-- Backend selection (set DATABASE_URL in .env):
--   SQLite (default) : sqlite:///users.db
--   MySQL            : mysql+pymysql://user:pass@host/qa_chat_tester
--
-- All operational data (logs, cases, insights, accounts,
-- conversations) lives in MongoDB — see db/repositories/.
-- ============================================================


-- ── MySQL version ────────────────────────────────────────────
-- Run only when DATABASE_URL points to MySQL.

CREATE TABLE IF NOT EXISTS users (
    user_id       INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    email         VARCHAR(255)    NOT NULL,
    password VARCHAR(64)     NOT NULL COMMENT 'SHA-256(salt:password)',
    name          VARCHAR(255)    DEFAULT NULL,
    created_at    DATETIME        NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME        NOT NULL  DEFAULT CURRENT_TIMESTAMP
                                            ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (user_id),
    UNIQUE KEY uq_users_email        (email),
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci;


-- ── SQLite equivalent (for reference) ────────────────────────
-- SQLite does not support ON UPDATE triggers inline, but
-- SQLAlchemy handles updated_at via the onupdate= parameter.
--
-- CREATE TABLE IF NOT EXISTS users (
--     user_id       INTEGER  PRIMARY KEY AUTOINCREMENT,
--     email         TEXT     NOT NULL UNIQUE,
--     password TEXT     NOT NULL,
--     name          TEXT,
--     created_at    TEXT     NOT NULL,
--     updated_at    TEXT     NOT NULL
-- );
