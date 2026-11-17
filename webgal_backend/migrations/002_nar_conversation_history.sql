-- NarAgent conversation history, MySQL 8.0+, utf8mb4, UTC.
-- Apply MANUALLY after review. Application never auto-migrates.
-- Enable NAR_CONVERSATIONS_ENABLED=1 only after verifying this migration.
CREATE TABLE IF NOT EXISTS nar_conversations (
  id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
  owner_id VARCHAR(191) NOT NULL,
  title VARCHAR(160) NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  active_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY idx_nar_conversations_owner_active (owner_id, active_at DESC, id DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS nar_messages (
  id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
  conversation_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  seq INT UNSIGNED NOT NULL,
  role ENUM('user', 'assistant') NOT NULL,
  content TEXT NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  turn_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL,
  public_metadata JSON DEFAULT NULL,
  UNIQUE KEY uq_nar_messages_conversation_seq (conversation_id, seq),
  KEY idx_nar_messages_turn (turn_id),
  CONSTRAINT fk_nar_messages_conversation FOREIGN KEY (conversation_id) REFERENCES nar_conversations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS nar_turns (
  id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
  conversation_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  client_request_id VARCHAR(80) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  prompt_message_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  mode ENUM('chat', 'html', 'animation', 'edit') NOT NULL,
  status ENUM('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'UNKNOWN') NOT NULL DEFAULT 'QUEUED',
  agent_run_id VARCHAR(80) DEFAULT NULL,
  parent_artifact_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL,
  error_code VARCHAR(80) DEFAULT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  finished_at DATETIME(6) DEFAULT NULL,
  UNIQUE KEY uq_nar_turns_idempotency (conversation_id, client_request_id),
  KEY idx_nar_turns_conversation_status (conversation_id, status, created_at),
  CONSTRAINT fk_nar_turns_conversation FOREIGN KEY (conversation_id) REFERENCES nar_conversations(id) ON DELETE CASCADE,
  CONSTRAINT fk_nar_turns_prompt FOREIGN KEY (prompt_message_id) REFERENCES nar_messages(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Outbox records are committed with user message + turn. Dispatch cannot be
-- safely retried until NarAgent accepts durable idempotency keys itself.
CREATE TABLE IF NOT EXISTS nar_turn_dispatches (
  turn_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
  state ENUM('PENDING', 'ACKNOWLEDGED', 'UNCERTAIN', 'FINISHED') NOT NULL DEFAULT 'PENDING',
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  acknowledged_at DATETIME(6) DEFAULT NULL,
  CONSTRAINT fk_nar_dispatch_turn FOREIGN KEY (turn_id) REFERENCES nar_turns(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS nar_conversation_artifacts (
  conversation_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  artifact_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  origin_message_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL,
  work_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL,
  title VARCHAR(160) NOT NULL,
  kind ENUM('html', 'animation') NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (conversation_id, artifact_id),
  KEY idx_nar_artifacts_lookup (artifact_id, created_at DESC),
  KEY idx_nar_artifacts_created (created_at DESC, artifact_id, conversation_id),
  CONSTRAINT fk_nar_artifacts_conversation FOREIGN KEY (conversation_id) REFERENCES nar_conversations(id) ON DELETE CASCADE,
  CONSTRAINT fk_nar_artifacts_message FOREIGN KEY (origin_message_id) REFERENCES nar_messages(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
