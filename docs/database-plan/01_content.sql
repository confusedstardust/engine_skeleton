-- NarrativeOS: content foundation. MySQL 5.7.44 / InnoDB.
-- Run once after 00_preflight.sql against a reviewed database with existing users.
-- No IF NOT EXISTS: schema drift must fail visibly. DDL is NOT transactional.
-- All application connections must set time_zone='+00:00' and strict SQL mode.
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;
SET time_zone = '+00:00';

CREATE TABLE games (
  id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  owner_user_id VARCHAR(191) NOT NULL,
  title VARCHAR(200) NOT NULL,
  description TEXT NULL,
  slug VARCHAR(96) CHARACTER SET ascii COLLATE ascii_bin NULL,
  status ENUM('DRAFT','PUBLISHED','ARCHIVED','BLOCKED') NOT NULL DEFAULT 'DRAFT',
  visibility ENUM('PRIVATE','UNLISTED','PUBLIC') NOT NULL DEFAULT 'PRIVATE',
  current_version_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '当前线上版本；只能通过发布事务切换',
  cover_file_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL,
  like_count BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '关系表的可重建缓存',
  favorite_count BIGINT UNSIGNED NOT NULL DEFAULT 0,
  lock_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
  first_published_at DATETIME(3) NULL,
  last_published_at DATETIME(3) NULL,
  deleted_at DATETIME(3) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uq_game_owner (id, owner_user_id),
  UNIQUE KEY uq_game_slug (slug),
  KEY ix_game_owner_list (owner_user_id, deleted_at, updated_at, id),
  KEY ix_game_public_list (status, visibility, deleted_at, last_published_at, id),
  CONSTRAINT fk_game_owner FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='作品稳定身份；一个作品有多个任务和发布版本';

CREATE TABLE generation_jobs (
  id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '沿用现有 job_id',
  game_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  owner_user_id VARCHAR(191) NOT NULL,
  request_key VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  request_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '规范化请求哈希；同键异参返回409',
  status ENUM('CREATED','QUEUED','RUNNING','WAITING_INPUT','SUCCEEDED','FAILED','CANCELLED') NOT NULL DEFAULT 'CREATED',
  phase VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  legacy_status VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '迁移保留旧 *_READY 等值',
  progress_percent TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '服务保证0..100',
  draft_revision BIGINT UNSIGNED NOT NULL DEFAULT 0,
  published_revision BIGINT UNSIGNED NOT NULL DEFAULT 0,
  build_state VARCHAR(24) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'NONE',
  dirty_scopes JSON NULL,
  options_json JSON NULL,
  artifact_manifest_json JSON NULL,
  job_storage_prefix VARCHAR(1024) COLLATE utf8mb4_bin NOT NULL COMMENT '本地相对路径或对象前缀；不存签名URL',
  source_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  error_code VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  error_message TEXT NULL COMMENT '脱敏；完整堆栈放受限日志',
  attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
  lock_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
  lease_token CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL,
  lease_expires_at DATETIME(3) NULL,
  heartbeat_at DATETIME(3) NULL,
  started_at DATETIME(3) NULL,
  finished_at DATETIME(3) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uq_job_request (owner_user_id, request_key),
  UNIQUE KEY uq_job_game (id, game_id),
  UNIQUE KEY uq_job_owner (id, owner_user_id),
  KEY ix_job_game_time (game_id, created_at, id),
  KEY ix_job_owner_time (owner_user_id, created_at, id),
  KEY ix_job_worker (status, lease_expires_at, id),
  CONSTRAINT fk_job_game_owner FOREIGN KEY (game_id, owner_user_id) REFERENCES games(id, owner_user_id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='生成执行实例；数据库接入后作为业务状态权威';

CREATE TABLE game_versions (
  id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  game_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  source_job_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  version_no INT UNSIGNED NOT NULL COMMENT '作品内单调递增；锁住games分配',
  source_draft_revision BIGINT UNSIGNED NOT NULL,
  version_label VARCHAR(64) NULL,
  release_notes TEXT NULL,
  status ENUM('BUILDING','READY','FAILED','REVOKED') NOT NULL DEFAULT 'BUILDING',
  review_status ENUM('PENDING','APPROVED','REJECTED') NOT NULL DEFAULT 'PENDING',
  review_reason VARCHAR(1000) NULL,
  reviewed_at DATETIME(3) NULL,
  reviewed_by_user_id VARCHAR(191) NULL,
  engine_version VARCHAR(64) NOT NULL,
  manifest_json JSON NULL COMMENT '相对路径到不可变asset_file的映射',
  manifest_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  build_storage_prefix VARCHAR(1024) COLLATE utf8mb4_bin NULL COMMENT '必须含version_id，不覆盖',
  entrypoint VARCHAR(255) NOT NULL DEFAULT 'index.html',
  published_at DATETIME(3) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uq_version_number (game_id, version_no),
  UNIQUE KEY uq_version_game (id, game_id),
  KEY ix_version_job_game (source_job_id, game_id),
  CONSTRAINT fk_version_game FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE RESTRICT,
  CONSTRAINT fk_version_job_game FOREIGN KEY (source_job_id, game_id) REFERENCES generation_jobs(id, game_id) ON DELETE RESTRICT,
  CONSTRAINT fk_version_reviewer FOREIGN KEY (reviewed_by_user_id) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='发布快照；READY后内容不可编辑，状态和审核可变';

CREATE TABLE assets (
  id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  owner_user_id VARCHAR(191) NOT NULL,
  source_job_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL,
  name VARCHAR(200) NOT NULL,
  kind ENUM('BACKGROUND','FIGURE','AVATAR','VOICE','BGM','SFX','VIDEO','SCRIPT','OTHER') NOT NULL,
  source_type ENUM('GENERATED','UPLOADED','IMPORTED') NOT NULL,
  visibility ENUM('PRIVATE','PUBLIC') NOT NULL DEFAULT 'PRIVATE',
  status ENUM('ACTIVE','BLOCKED','DELETED') NOT NULL DEFAULT 'ACTIVE',
  license_code VARCHAR(64) NULL COMMENT '公开展示不代表允许他人复用',
  attribution TEXT NULL,
  generation_metadata JSON NULL COMMENT '模型、参数、seed；敏感prompt单独受控',
  deleted_at DATETIME(3) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY ix_asset_library (owner_user_id, status, kind, created_at, id),
  KEY ix_asset_source (source_job_id, owner_user_id),
  CONSTRAINT fk_asset_owner FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_asset_job_owner FOREIGN KEY (source_job_id, owner_user_id) REFERENCES generation_jobs(id, owner_user_id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='逻辑素材；跨作品复用，来源和授权可追溯';

CREATE TABLE asset_files (
  id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  asset_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  revision INT UNSIGNED NOT NULL DEFAULT 1,
  variant VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'original',
  storage_provider ENUM('LOCAL','OSS') NOT NULL,
  bucket VARCHAR(63) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT '' COMMENT 'LOCAL用空串',
  region VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  object_key VARCHAR(1024) COLLATE utf8mb4_bin NOT NULL COMMENT 'OSS key或受限本地相对路径',
  object_version_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT '' COMMENT '未开启OSS版本控制用空串',
  location_hash BINARY(32) NOT NULL COMMENT 'SHA256规范元组(provider,bucket,key,version)，服务生成并逐项比对',
  sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '文件内容哈希；不能用ETag代替',
  etag VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NULL,
  mime_type VARCHAR(127) NOT NULL,
  size_bytes BIGINT UNSIGNED NOT NULL,
  width_px INT UNSIGNED NULL,
  height_px INT UNSIGNED NULL,
  duration_ms BIGINT UNSIGNED NULL,
  status ENUM('UPLOADING','READY','FAILED','DELETING','DELETED') NOT NULL DEFAULT 'UPLOADING',
  uploaded_at DATETIME(3) NULL,
  delete_after DATETIME(3) NULL,
  deleted_at DATETIME(3) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uq_asset_variant (asset_id, revision, variant),
  UNIQUE KEY uq_file_location (location_hash),
  KEY ix_file_gc (status, delete_after, id),
  KEY ix_file_checksum (sha256),
  CONSTRAINT fk_file_asset FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='物理文件不可变；URL按权限临时生成';

CREATE TABLE asset_usages (
  game_version_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  logical_path VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '版本内相对路径；禁止..和绝对路径',
  asset_file_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  usage_role VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (game_version_id, logical_path),
  KEY ix_usage_file (asset_file_id),
  CONSTRAINT fk_usage_version FOREIGN KEY (game_version_id) REFERENCES game_versions(id) ON DELETE RESTRICT,
  CONSTRAINT fk_usage_file FOREIGN KEY (asset_file_id) REFERENCES asset_files(id) ON DELETE RESTRICT
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='版本精确引用文件revision，防止重生成破坏旧作品';

ALTER TABLE games
  ADD KEY ix_game_current (current_version_id, id),
  ADD CONSTRAINT fk_game_current FOREIGN KEY (current_version_id, id) REFERENCES game_versions(id, game_id) ON DELETE RESTRICT,
  ADD CONSTRAINT fk_game_cover FOREIGN KEY (cover_file_id) REFERENCES asset_files(id) ON DELETE RESTRICT;

CREATE TABLE game_likes (
  game_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  user_id VARCHAR(191) NOT NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (game_id, user_id),
  KEY ix_like_user (user_id, created_at, game_id),
  CONSTRAINT fk_like_game FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE RESTRICT,
  CONSTRAINT fk_like_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='点赞事实；取消时删除这一条关系';

CREATE TABLE game_favorites (
  game_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  user_id VARCHAR(191) NOT NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (game_id, user_id),
  KEY ix_favorite_user (user_id, created_at, game_id),
  CONSTRAINT fk_favorite_game FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE RESTRICT,
  CONSTRAINT fk_favorite_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='收藏默认仅本人可见；总数可公开';

CREATE TABLE outbox_events (
  id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  event_key VARCHAR(191) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  event_type VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  aggregate_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  payload_json JSON NOT NULL COMMENT '只放必要ID与版本，不放密钥和支付明文',
  status ENUM('PENDING','PROCESSING','DONE','DEAD') NOT NULL DEFAULT 'PENDING',
  attempts INT UNSIGNED NOT NULL DEFAULT 0,
  available_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  lease_token CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL,
  lease_expires_at DATETIME(3) NULL,
  last_error VARCHAR(1000) NULL,
  processed_at DATETIME(3) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uq_outbox_event (event_key),
  KEY ix_outbox_poll (status, available_at, id),
  KEY ix_outbox_lease (status, lease_expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='与业务写入同事务；投递至少一次，消费者必须幂等';
