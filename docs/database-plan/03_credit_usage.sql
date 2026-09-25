-- Required only when selling generation credits. Requires 01 + 02.
-- Credits are service units, NOT money and NOT a withdrawable wallet.
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;
SET time_zone = '+00:00';

CREATE TABLE credit_reservations (
  id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  user_id VARCHAR(191) NOT NULL,
  job_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  operation_key VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '同一job的首次生成/不同重生成操作独立计费',
  units BIGINT UNSIGNED NOT NULL,
  status ENUM('RESERVED','CAPTURED','RELEASED') NOT NULL DEFAULT 'RESERVED',
  active_job_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin GENERATED ALWAYS AS
    (CASE WHEN status='RESERVED' THEN job_id ELSE NULL END) STORED,
  pricing_snapshot JSON NOT NULL,
  settled_at DATETIME(3) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uq_credit_operation (job_id, operation_key),
  UNIQUE KEY uq_credit_active_job (active_job_id),
  UNIQUE KEY uq_reservation_user (id, user_id),
  KEY ix_reservation_user (user_id, status, created_at),
  CONSTRAINT fk_reservation_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_reservation_job FOREIGN KEY (job_id, user_id) REFERENCES generation_jobs(id, owner_user_id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='冻结额度后启动任务；成功核销，确定失败释放';

CREATE TABLE credit_allocations (
  reservation_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  grant_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  user_id VARCHAR(191) NOT NULL,
  units BIGINT UNSIGNED NOT NULL,
  PRIMARY KEY (reservation_id, grant_id),
  KEY ix_allocation_grant_user (grant_id, user_id),
  KEY ix_allocation_reservation_user (reservation_id, user_id),
  CONSTRAINT fk_allocation_reservation FOREIGN KEY (reservation_id, user_id) REFERENCES credit_reservations(id, user_id) ON DELETE RESTRICT,
  CONSTRAINT fk_allocation_grant FOREIGN KEY (grant_id, user_id) REFERENCES entitlement_grants(id, user_id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='一次消费可占多个额度批次；支持退款溯源';

CREATE TABLE credit_ledger (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  event_key VARCHAR(191) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  grant_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  reservation_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL,
  user_id VARCHAR(191) NOT NULL,
  action ENUM('GRANT','RESERVE','CAPTURE','RELEASE','REVOKE','EXPIRE') NOT NULL,
  delta_available BIGINT NOT NULL,
  delta_reserved BIGINT NOT NULL,
  delta_consumed BIGINT NOT NULL,
  delta_revoked BIGINT NOT NULL,
  available_after BIGINT UNSIGNED NOT NULL,
  reserved_after BIGINT UNSIGNED NOT NULL,
  consumed_after BIGINT UNSIGNED NOT NULL,
  revoked_after BIGINT UNSIGNED NOT NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uq_credit_event_grant (event_key, grant_id),
  KEY ix_ledger_user (user_id, created_at, id),
  KEY ix_ledger_grant_user (grant_id, user_id),
  KEY ix_ledger_reservation_user (reservation_id, user_id),
  CONSTRAINT fk_ledger_grant FOREIGN KEY (grant_id, user_id) REFERENCES entitlement_grants(id, user_id) ON DELETE RESTRICT,
  CONSTRAINT fk_ledger_reservation FOREIGN KEY (reservation_id, user_id) REFERENCES credit_reservations(id, user_id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='只追加，禁止改历史流水；与批次余额在同一事务';
