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
    password_hash VARCHAR(64)     NOT NULL COMMENT 'SHA-256(salt:password)',
    name          VARCHAR(255)    DEFAULT NULL,
    account_id    VARCHAR(255)    NOT NULL  COMMENT 'Tenant FK → MongoDB accounts.account_id',
    is_active     TINYINT(1)      NOT NULL  DEFAULT 1,
    created_at    DATETIME        NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME        NOT NULL  DEFAULT CURRENT_TIMESTAMP
                                            ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (user_id),
    UNIQUE KEY uq_users_email        (email),
    INDEX       idx_users_account_id (account_id)
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
--     password_hash TEXT     NOT NULL,
--     name          TEXT,
--     account_id    TEXT     NOT NULL,
--     is_active     INTEGER  NOT NULL DEFAULT 1,
--     created_at    TEXT     NOT NULL,
--     updated_at    TEXT     NOT NULL
-- );
-- CREATE INDEX IF NOT EXISTS idx_users_account_id ON users (account_id);
