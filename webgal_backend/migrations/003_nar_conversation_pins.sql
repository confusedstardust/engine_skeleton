-- Apply manually before deploying conversation management UI/API.
-- Requires MySQL 8.0+ and the previous 002_nar_conversation_history.sql schema.
ALTER TABLE nar_conversations
  ADD COLUMN is_pinned TINYINT(1) NOT NULL DEFAULT 0 AFTER title;

CREATE INDEX idx_nar_conversations_owner_pinned_active
  ON nar_conversations (owner_id, is_pinned DESC, active_at DESC, id DESC);
