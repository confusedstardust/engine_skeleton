-- OPTIONAL coordinated auth-service release. NOT part of content-only rollout.
-- Preconditions: supplied PDF baseline; confirm actual lengths/collations first.
-- Preserve Prisma ownership: update its models and create a reviewed migration.
-- Adding fields alone does NOT implement session revocation or account suspension.
SET time_zone = '+00:00';

ALTER TABLE users
  MODIFY avatar_url VARCHAR(2048) NULL,
  ADD COLUMN status ENUM('ACTIVE','SUSPENDED','CLOSED') NOT NULL DEFAULT 'ACTIVE',
  ADD COLUMN bio VARCHAR(1000) NULL,
  ADD COLUMN last_login_at DATETIME(3) NULL,
  ADD COLUMN password_changed_at DATETIME(3) NULL,
  ADD COLUMN deleted_at DATETIME(3) NULL;

ALTER TABLE auth_sessions
  ADD COLUMN revoked_at DATETIME(3) NULL,
  ADD COLUMN last_seen_at DATETIME(3) NULL,
  ADD KEY ix_session_expiry (expires_at);

ALTER TABLE verification_codes
  ADD COLUMN purpose VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'LOGIN',
  ADD KEY ix_code_lookup (email, purpose, created_at),
  ADD KEY ix_code_expiry (expires_at);

-- accounts.provider scope / AppID migration is deliberately NOT automatic.
-- See PLAN.md: historical WeChat AppID must be identified before changing uniqueness.
-- No changes to _prisma_migrations. No dropping old indexes in this expand phase.
