-- Database-backed Forge job state. Run once after 01_content.sql.
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;
SET time_zone = '+00:00';

ALTER TABLE generation_jobs
  ADD COLUMN source_material MEDIUMTEXT NULL AFTER owner_user_id;

CREATE TABLE generation_job_events (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  job_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  event_type VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  status VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  phase VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  message TEXT NULL,
  metadata_json JSON NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY ix_job_event_time (job_id, created_at, id),
  CONSTRAINT fk_job_event_job FOREIGN KEY (job_id)
    REFERENCES generation_jobs(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='生成任务状态与错误历史；generation_jobs保存当前快照';
