from __future__ import annotations

import hashlib
import json
import mimetypes
import uuid
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any, Iterator

from credit_system.config import CreditDatabaseConfig

from .config import settings


class AssetLibraryError(RuntimeError):
    pass


def _location_hash(provider: str, bucket: str, key: str, version: str = "") -> bytes:
    return hashlib.sha256("\x1f".join((provider, bucket, key, version)).encode("utf-8")).digest()


def _public_url(key: str) -> str:
    return f"https://{settings.oss_bucket}.oss-cn-hangzhou.aliyuncs.com/{key}"


class AssetLibrary:
    """Immutable OSS registry: generated assets are shared, uploads stay private."""

    def __init__(self, config: CreditDatabaseConfig | None = None) -> None:
        self.config = config or CreditDatabaseConfig.from_env()

    @contextmanager
    def _transaction(self) -> Iterator[Any]:
        try:
            import pymysql
            from pymysql.cursors import DictCursor
        except ImportError as exc:  # pragma: no cover
            raise AssetLibraryError("PyMySQL is required") from exc
        connection = pymysql.connect(cursorclass=DictCursor, **self.config.connect_kwargs())
        try:
            connection.begin()
            with connection.cursor() as cursor:
                yield cursor
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _bucket(self):
        if not settings.oss_bucket or not settings.oss_access_key_id or not settings.oss_access_key_secret:
            raise AssetLibraryError("OSS is not configured")
        try:
            import oss2
        except ImportError as exc:  # pragma: no cover
            raise AssetLibraryError("OSS client dependency is missing") from exc
        return oss2.Bucket(
            oss2.Auth(settings.oss_access_key_id, settings.oss_access_key_secret),
            settings.oss_endpoint,
            settings.oss_bucket,
        )

    def publish_file(
        self,
        *,
        user_id: str,
        job_id: str,
        path: Path,
        logical_path: str,
        kind: str,
        source_type: str,
        name: str,
        usage_role: str,
        source_key: str,
        variant: str = "original",
        metadata: dict[str, Any] | None = None,
        width: int | None = None,
        height: int | None = None,
        duration_ms: int | None = None,
    ) -> dict[str, Any]:
        if source_type not in {"GENERATED", "UPLOADED"}:
            raise AssetLibraryError("Unsupported asset source type")
        content = path.read_bytes()
        sha256 = hashlib.sha256(content).hexdigest()
        asset_id = hashlib.sha256(f"{user_id}\x1f{source_type}\x1f{source_key}".encode()).hexdigest()[:32]
        file_id = uuid.uuid4().hex
        suffix = path.suffix.lower()
        owner_key = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:24]
        object_key = str(PurePosixPath(settings.oss_prefix) / "library" / owner_key / asset_id / file_id / f"{variant}{suffix}")
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        bucket = self._bucket()
        try:
            result = bucket.put_object(object_key, content, headers={"Content-Type": mime_type})
        except Exception as exc:
            raise AssetLibraryError("upload to OSS failed") from exc
        etag = str(getattr(result, "etag", "") or "") or None

        try:
            with self._transaction() as cursor:
                cursor.execute("SELECT id FROM generation_jobs WHERE id=%s AND owner_user_id=%s", (job_id, user_id))
                if cursor.fetchone() is None:
                    raise AssetLibraryError("The job is not registered for this user")
                cursor.execute(
                    "SELECT id FROM assets WHERE owner_user_id=%s AND source_type=%s AND source_key=%s FOR UPDATE",
                    (user_id, source_type, source_key),
                )
                existing = cursor.fetchone()
                visibility = "PUBLIC" if source_type == "GENERATED" else "PRIVATE"
                if existing:
                    asset_id = existing["id"]
                    cursor.execute(
                        "UPDATE assets SET name=%s, kind=%s, visibility=%s, status='ACTIVE', generation_metadata=%s WHERE id=%s",
                        (name[:200], kind, visibility, json.dumps(metadata, ensure_ascii=False) if metadata else None, asset_id),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO assets
                            (id, owner_user_id, source_job_id, name, kind, source_type, visibility,
                             status, generation_metadata, source_key)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,'ACTIVE',%s,%s)
                        """,
                        (asset_id, user_id, job_id, name[:200], kind, source_type, visibility,
                         json.dumps(metadata, ensure_ascii=False) if metadata else None, source_key),
                    )
                cursor.execute(
                    "SELECT COALESCE(MAX(revision),0)+1 AS next_revision FROM asset_files WHERE asset_id=%s AND variant=%s",
                    (asset_id, variant),
                )
                revision = int(cursor.fetchone()["next_revision"])
                cursor.execute(
                    """
                    INSERT INTO asset_files
                        (id, asset_id, revision, variant, storage_provider, bucket, region, object_key,
                         location_hash, sha256, etag, mime_type, size_bytes, width_px, height_px,
                         duration_ms, status, uploaded_at)
                    VALUES (%s,%s,%s,%s,'OSS',%s,'oss-cn-hangzhou',%s,%s,%s,%s,%s,%s,%s,%s,%s,
                            'READY',CURRENT_TIMESTAMP(3))
                    """,
                    (file_id, asset_id, revision, variant, settings.oss_bucket, object_key,
                     _location_hash("OSS", settings.oss_bucket or "", object_key), sha256, etag,
                     mime_type, len(content), width, height, duration_ms),
                )
                cursor.execute(
                    """
                    INSERT INTO draft_asset_usages
                        (job_id, user_id, logical_path, asset_file_id, usage_role)
                    VALUES (%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE asset_file_id=VALUES(asset_file_id), usage_role=VALUES(usage_role)
                    """,
                    (job_id, user_id, logical_path, file_id, usage_role[:32]),
                )
        except Exception:
            try:
                bucket.delete_object(object_key)
            except Exception:
                pass
            raise
        return {
            "asset_id": asset_id,
            "asset_file_id": file_id,
            "revision": revision,
            "variant": variant,
            "oss_key": object_key,
            "oss_url": _public_url(object_key),
        }

    def list_assets(
        self,
        user_id: str,
        *,
        kind: str | None = None,
        source_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if source_type == "GENERATED":
            # GENERATED is globally reusable by product definition. Do not hide legacy
            # generated rows that predate the PUBLIC visibility migration.
            where = "a.source_type='GENERATED' AND a.status='ACTIVE' AND f.status='READY'"
            params: list[Any] = []
        else:
            where = "a.owner_user_id=%s AND a.status='ACTIVE' AND f.status='READY'"
            params = [user_id]
        if kind:
            where += " AND a.kind=%s"
            params.append(kind)
        if source_type and source_type != "GENERATED":
            where += " AND a.source_type=%s"
            params.append(source_type)
        params.append(max(1, min(limit, 200)))
        with self._transaction() as cursor:
            cursor.execute(
                f"""
                SELECT a.id, a.owner_user_id, a.name, a.kind, a.source_type, a.visibility,
                       a.source_job_id, a.created_at,
                       f.id AS file_id, f.revision, f.variant, f.mime_type, f.size_bytes,
                       f.width_px, f.height_px, f.duration_ms, f.object_key
                FROM assets a
                JOIN asset_files f ON f.asset_id=a.id
                JOIN (
                    SELECT asset_id, variant, MAX(revision) revision
                    FROM asset_files WHERE status='READY' GROUP BY asset_id, variant
                ) latest ON latest.asset_id=f.asset_id AND latest.variant=f.variant AND latest.revision=f.revision
                WHERE {where}
                ORDER BY a.updated_at DESC, a.id DESC, f.variant ASC
                LIMIT %s
                """,
                tuple(params),
            )
            rows = cursor.fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["url"] = _public_url(item.pop("object_key"))
            for key in ("created_at",):
                if item.get(key) is not None:
                    item[key] = item[key].isoformat()
            result.append(item)
        return result

    def get_owned_file(self, user_id: str, file_id: str) -> dict[str, Any]:
        with self._transaction() as cursor:
            cursor.execute(
                """
                SELECT f.*, a.name, a.kind, a.source_type, a.id AS asset_id
                FROM asset_files f JOIN assets a ON a.id=f.asset_id
                WHERE f.id=%s AND a.owner_user_id=%s AND a.status='ACTIVE' AND f.status='READY'
                """,
                (file_id, user_id),
            )
            row = cursor.fetchone()
        if not row:
            raise AssetLibraryError("Asset file not found")
        return dict(row)

    def rename_asset(self, user_id: str, asset_id: str, name: str) -> dict[str, Any]:
        normalized_name = name.strip()
        if not normalized_name:
            raise AssetLibraryError("Asset name is required")
        with self._transaction() as cursor:
            cursor.execute(
                "UPDATE assets SET name=%s WHERE id=%s AND owner_user_id=%s AND status='ACTIVE'",
                (normalized_name[:200], asset_id, user_id),
            )
            if cursor.rowcount != 1:
                raise AssetLibraryError("Asset not found")
            cursor.execute(
                "SELECT id, name, kind, source_type FROM assets WHERE id=%s AND owner_user_id=%s",
                (asset_id, user_id),
            )
            row = cursor.fetchone()
        return dict(row)

    def delete_asset(self, user_id: str, asset_id: str) -> None:
        # Keep immutable files available for already-published game versions, but
        # remove the logical asset from the owner's active personal library.
        with self._transaction() as cursor:
            cursor.execute(
                "UPDATE assets SET status='DELETED' WHERE id=%s AND owner_user_id=%s AND status='ACTIVE'",
                (asset_id, user_id),
            )
            if cursor.rowcount != 1:
                raise AssetLibraryError("Asset not found")

    def get_accessible_file(self, user_id: str, file_id: str) -> dict[str, Any]:
        with self._transaction() as cursor:
            cursor.execute(
                """
                SELECT f.*, a.name, a.kind, a.source_type, a.visibility, a.owner_user_id,
                       a.id AS asset_id
                FROM asset_files f JOIN assets a ON a.id=f.asset_id
                WHERE f.id=%s
                  AND (a.owner_user_id=%s OR a.source_type='GENERATED')
                  AND a.status='ACTIVE' AND f.status='READY'
                """,
                (file_id, user_id),
            )
            row = cursor.fetchone()
        if not row:
            raise AssetLibraryError("Asset file not found")
        return dict(row)

    def runtime_urls_for_job(self, user_id: str, job_id: str) -> dict[str, str]:
        with self._transaction() as cursor:
            cursor.execute(
                """
                SELECT d.logical_path, f.bucket, f.object_key
                FROM draft_asset_usages d
                JOIN asset_files f ON f.id=d.asset_file_id
                JOIN assets a ON a.id=f.asset_id
                WHERE d.job_id=%s AND d.user_id=%s
                  AND a.status='ACTIVE' AND f.status='READY' AND f.storage_provider='OSS'
                """,
                (job_id, user_id),
            )
            rows = cursor.fetchall()
        return {
            str(row["logical_path"]): f"https://{row['bucket']}.oss-cn-hangzhou.aliyuncs.com/{row['object_key']}"
            for row in rows
        }

    def download_owned_file(self, user_id: str, file_id: str) -> tuple[dict[str, Any], bytes]:
        record = self.get_owned_file(user_id, file_id)
        try:
            content = self._bucket().get_object(record["object_key"]).read()
        except Exception as exc:
            raise AssetLibraryError("Could not download asset from OSS") from exc
        return record, content

    def download_accessible_file(self, user_id: str, file_id: str) -> tuple[dict[str, Any], bytes]:
        record = self.get_accessible_file(user_id, file_id)
        try:
            content = self._bucket().get_object(record["object_key"]).read()
        except Exception as exc:
            raise AssetLibraryError("Could not download asset from OSS") from exc
        return record, content

    def download_owned_variant(self, user_id: str, asset_id: str, variant: str) -> tuple[dict[str, Any], bytes] | None:
        with self._transaction() as cursor:
            cursor.execute(
                """
                SELECT f.*, a.name, a.kind, a.id AS asset_id
                FROM asset_files f JOIN assets a ON a.id=f.asset_id
                WHERE a.id=%s AND a.owner_user_id=%s AND a.status='ACTIVE'
                  AND f.variant=%s AND f.status='READY'
                ORDER BY f.revision DESC LIMIT 1
                """,
                (asset_id, user_id, variant),
            )
            record = cursor.fetchone()
        if not record:
            return None
        try:
            content = self._bucket().get_object(record["object_key"]).read()
        except Exception as exc:
            raise AssetLibraryError("Could not download asset from OSS") from exc
        return dict(record), content

    def download_accessible_variant(self, user_id: str, asset_id: str, variant: str) -> tuple[dict[str, Any], bytes] | None:
        with self._transaction() as cursor:
            cursor.execute(
                """
                SELECT f.*, a.name, a.kind, a.source_type, a.visibility, a.owner_user_id,
                       a.id AS asset_id
                FROM asset_files f JOIN assets a ON a.id=f.asset_id
                WHERE a.id=%s
                  AND (a.owner_user_id=%s OR a.source_type='GENERATED')
                  AND a.status='ACTIVE' AND f.variant=%s AND f.status='READY'
                ORDER BY f.revision DESC LIMIT 1
                """,
                (asset_id, user_id, variant),
            )
            record = cursor.fetchone()
        if not record:
            return None
        try:
            content = self._bucket().get_object(record["object_key"]).read()
        except Exception as exc:
            raise AssetLibraryError("Could not download asset from OSS") from exc
        return dict(record), content

    def record_draft_usage(self, *, user_id: str, job_id: str, logical_path: str, file_id: str, usage_role: str) -> None:
        with self._transaction() as cursor:
            cursor.execute(
                "SELECT 1 FROM generation_jobs WHERE id=%s AND owner_user_id=%s",
                (job_id, user_id),
            )
            if cursor.fetchone() is None:
                raise AssetLibraryError("The job is not registered for this user")
            cursor.execute(
                """
                INSERT INTO draft_asset_usages (job_id,user_id,logical_path,asset_file_id,usage_role)
                VALUES (%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE asset_file_id=VALUES(asset_file_id), usage_role=VALUES(usage_role)
                """,
                (job_id, user_id, logical_path, file_id, usage_role[:32]),
            )

    def publish_game_version(self, *, user_id: str, job_id: str, draft_revision: int, engine_version: str = "4.6.0") -> str:
        version_id = uuid.uuid4().hex
        with self._transaction() as cursor:
            cursor.execute(
                "SELECT game_id FROM generation_jobs WHERE id=%s AND owner_user_id=%s FOR UPDATE",
                (job_id, user_id),
            )
            job = cursor.fetchone()
            if not job:
                raise AssetLibraryError("The job is not registered for this user")
            game_id = str(job["game_id"])
            cursor.execute("SELECT COALESCE(MAX(version_no),0)+1 AS version_no FROM game_versions WHERE game_id=%s", (game_id,))
            version_no = int(cursor.fetchone()["version_no"])
            cursor.execute(
                """
                SELECT d.logical_path, d.asset_file_id, d.usage_role, f.sha256
                FROM draft_asset_usages d JOIN asset_files f ON f.id=d.asset_file_id
                WHERE d.job_id=%s AND d.user_id=%s ORDER BY d.logical_path
                """,
                (job_id, user_id),
            )
            usages = cursor.fetchall()
            manifest = {
                "schema_version": 1,
                "assets": [
                    {"logical_path": row["logical_path"], "asset_file_id": row["asset_file_id"], "usage_role": row["usage_role"], "sha256": row["sha256"]}
                    for row in usages
                ],
            }
            manifest_json = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            manifest_sha256 = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()
            cursor.execute(
                """
                INSERT INTO game_versions
                    (id,game_id,source_job_id,version_no,source_draft_revision,status,review_status,
                     engine_version,manifest_json,manifest_sha256,build_storage_prefix,entrypoint,published_at)
                VALUES (%s,%s,%s,%s,%s,'READY','PENDING',%s,%s,%s,%s,'index.html',CURRENT_TIMESTAMP(3))
                """,
                (version_id, game_id, job_id, version_no, max(0, draft_revision), engine_version,
                 manifest_json, manifest_sha256, f"jobs/{job_id}/versions/{version_id}"),
            )
            if usages:
                cursor.executemany(
                    "INSERT INTO asset_usages (game_version_id,logical_path,asset_file_id,usage_role) VALUES (%s,%s,%s,%s)",
                    [(version_id, row["logical_path"], row["asset_file_id"], row["usage_role"]) for row in usages],
                )
            cursor.execute(
                "UPDATE games SET current_version_id=%s, last_published_at=CURRENT_TIMESTAMP(3), first_published_at=COALESCE(first_published_at,CURRENT_TIMESTAMP(3)) WHERE id=%s",
                (version_id, game_id),
            )
            cursor.execute(
                "UPDATE generation_jobs SET draft_revision=%s,published_revision=%s,status='SUCCEEDED',progress_percent=100,finished_at=CURRENT_TIMESTAMP(3) WHERE id=%s",
                (max(0, draft_revision), max(0, draft_revision), job_id),
            )
        return version_id
