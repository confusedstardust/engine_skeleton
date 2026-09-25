-- Asset-library extension for 01_content.sql. Run once after reviewing existing data.
-- Adds an idempotent source key, draft references and the main library filter index.
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;
SET time_zone = '+00:00';

ALTER TABLE assets
  ADD COLUMN source_key VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL
    COMMENT '来源任务中的稳定逻辑键，例如figure/name或vocal/file',
  ADD KEY ix_asset_owner_source_kind
    (owner_user_id, status, source_type, kind, created_at, id),
  ADD UNIQUE KEY uq_asset_owner_source (owner_user_id, source_type, source_key);

ALTER TABLE asset_files
  ADD KEY ix_file_asset_variant_latest (asset_id, variant, status, revision, id);

CREATE TABLE draft_asset_usages (
  job_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  user_id VARCHAR(191) NOT NULL,
  logical_path VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  asset_file_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  usage_role VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (job_id, logical_path),
  KEY ix_draft_usage_file (asset_file_id),
  KEY ix_draft_usage_user (user_id, updated_at, job_id),
  CONSTRAINT fk_draft_usage_job_user FOREIGN KEY (job_id, user_id)
    REFERENCES generation_jobs(id, owner_user_id) ON DELETE RESTRICT,
  CONSTRAINT fk_draft_usage_file FOREIGN KEY (asset_file_id)
    REFERENCES asset_files(id) ON DELETE RESTRICT
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='草稿对确切素材文件的引用；发布时冻结为asset_usages';
