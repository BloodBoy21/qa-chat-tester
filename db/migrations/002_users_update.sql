-- ============================================================
-- Migration 002 — Users table update
-- Removes account_id (users are global admins).
-- Adds must_change_password flag.
-- ============================================================
-- Run only if upgrading from migration 001.
-- SQLAlchemy auto-applies these changes on fresh installs.
-- ============================================================

ALTER TABLE users
  DROP COLUMN  IF EXISTS account_id,
  ADD  COLUMN  IF NOT EXISTS must_change_password TINYINT(1) NOT NULL DEFAULT 1
    COMMENT 'Forces password change on next login';
