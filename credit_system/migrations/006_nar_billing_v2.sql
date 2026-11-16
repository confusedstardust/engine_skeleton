-- NarAgent Billing V2: additive structures. Apply only to the intended environment
-- after backup and schema review. CREATE IF NOT EXISTS avoids altering old ledgers.
-- Never backbill historical turns.
CREATE TABLE IF NOT EXISTS nar_usage_events (
  id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
  event_key VARCHAR(191) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  payload_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  owner_user_id VARCHAR(191) NOT NULL,
  conversation_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL,
  turn_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL,
  task_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL,
  call_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  attempt_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NULL,
  stage VARCHAR(32) NOT NULL,
  provider VARCHAR(64) NOT NULL,
  requested_model VARCHAR(128) NULL,
  actual_model VARCHAR(128) NULL,
  usage_status ENUM('REPORTED','PARTIAL','UNKNOWN','FAILED_PRE_SEND') NOT NULL,
  usage_source VARCHAR(64) NOT NULL,
  input_uncached BIGINT UNSIGNED NULL,
  cache_read_input BIGINT UNSIGNED NULL,
  cache_write_input BIGINT UNSIGNED NULL,
  output_total BIGINT UNSIGNED NULL,
  reasoning_output BIGINT UNSIGNED NULL,
  image_count INT UNSIGNED NULL,
  tts_characters BIGINT UNSIGNED NULL,
  tool_calls INT UNSIGNED NULL,
  provider_request_id VARCHAR(191) NULL,
  provider_cost_micro_usd DECIMAL(20,6) NULL,
  price_catalog_version VARCHAR(64) NULL,
  billable_to_user BOOLEAN NOT NULL DEFAULT FALSE,
  raw_usage_json JSON NULL,
  occurred_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_nar_usage_event_key (event_key),
  KEY idx_nar_usage_user_turn (owner_user_id, turn_id),
  KEY idx_nar_usage_conversation (owner_user_id, conversation_id),
  KEY idx_nar_usage_call (call_id),
  KEY idx_nar_usage_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS nar_task_billing (
  turn_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
  user_id VARCHAR(191) NOT NULL,
  billing_session_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL,
  budget_authorized_credits INT UNSIGNED NOT NULL DEFAULT 0,
  reserved_credits INT UNSIGNED NOT NULL DEFAULT 0,
  measured_microcredits DECIMAL(20,6) NOT NULL DEFAULT 0,
  final_credits INT UNSIGNED NULL,
  pricing_policy_version VARCHAR(64) NOT NULL,
  snapshot_json JSON NOT NULL,
  billing_status ENUM('PENDING','RESERVED','RUNNING','AWAITING_APPROVAL','RECONCILING',
    'CAPTURED','RELEASED','NEEDS_REVIEW') NOT NULL DEFAULT 'PENDING',
  usage_completeness ENUM('UNKNOWN','PARTIAL','COMPLETE') NOT NULL DEFAULT 'UNKNOWN',
  settlement_key VARCHAR(191) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_nar_task_billing_settlement (settlement_key),
  KEY idx_nar_task_billing_user (user_id, billing_status),
  KEY idx_nar_task_billing_session (billing_session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- This sequence is the caller's idempotency key for an authorized top-up.
CREATE TABLE IF NOT EXISTS nar_reservation_extensions (
  id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
  reservation_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  sequence_no INT UNSIGNED NOT NULL,
  delta_credits INT UNSIGNED NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_nar_reservation_extension (reservation_id,sequence_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS nar_price_catalog (
  version VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
  user_policy_json JSON NOT NULL,
  provider_catalog_json JSON NULL,
  source_url VARCHAR(512) NULL,
  effective_at DATETIME(6) NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
