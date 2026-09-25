from __future__ import annotations

import json
import hashlib
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import settings
from .database import database_connection


JOB_ID_RE = re.compile(r"^[a-f0-9]{32}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class JobStore:
    def __init__(self, jobs_dir: Path | None = None, *, database_enabled: bool | None = None) -> None:
        self.jobs_dir = jobs_dir or settings.jobs_dir
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.database_enabled = settings.database_job_store_enabled if database_enabled is None else database_enabled

    def create(
        self,
        source_material: str,
        options: dict[str, Any] | None = None,
        identity: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        job_id = uuid.uuid4().hex
        job_dir = self.job_dir(job_id)
        (job_dir / "state").mkdir(parents=True, exist_ok=True)
        (job_dir / "public" / "game" / "scene").mkdir(parents=True, exist_ok=True)
        (job_dir / "public" / "game" / "background").mkdir(parents=True, exist_ok=True)
        (job_dir / "public" / "game" / "figure").mkdir(parents=True, exist_ok=True)
        (job_dir / "public" / "game" / "bgm").mkdir(parents=True, exist_ok=True)

        job = {
            "id": job_id,
            "status": "CREATED",
            "phase": None,
            "source_material": source_material,
            "options": options or {},
            "identity": identity or {},
            "error": None,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "artifacts": {},
            "history": [],
            "draft_revision": 0,
            "published_revision": 0,
            "build_state": "NONE",
            "dirty_scopes": [],
            "has_published_build": False,
        }
        if self.database_enabled:
            self._create_database_job(job)
        else:
            self.save(job)
        return job

    def _create_database_job(self, job: dict[str, Any]) -> None:
        identity = job.get("identity") or {}
        if identity.get("type") != "sso" or not identity.get("user_id"):
            raise ValueError("database job store requires an authenticated NarrativeOS user")
        owner_user_id = str(identity["user_id"])
        game_id = uuid.uuid4().hex
        job["game_id"] = game_id
        title = str(job.get("options", {}).get("classroom_topic") or "").strip()
        if not title:
            title = next((line.strip() for line in str(job.get("source_material") or "").splitlines() if line.strip()), "未命名作品")
        title = title[:200]
        request_payload = json.dumps(
            {"source_material": job.get("source_material", ""), "options": job.get("options", {})},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        request_hash = hashlib.sha256(request_payload.encode("utf-8")).hexdigest()
        with database_connection() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT id FROM users WHERE id=%s", (owner_user_id,))
                    if not cursor.fetchone():
                        raise ValueError("logged-in user is not present in the NarrativeOS database")
                    cursor.execute(
                        "INSERT INTO games(id,owner_user_id,title,status,visibility) VALUES(%s,%s,%s,'DRAFT','PRIVATE')",
                        (game_id, owner_user_id, title),
                    )
                    cursor.execute(
                        """INSERT INTO generation_jobs
                        (id,game_id,owner_user_id,source_material,request_key,request_hash,status,legacy_status,
                         draft_revision,published_revision,build_state,dirty_scopes,options_json,
                         artifact_manifest_json,job_storage_prefix,source_sha256)
                        VALUES(%s,%s,%s,%s,%s,%s,'CREATED','CREATED',0,0,'NONE',JSON_ARRAY(),%s,JSON_OBJECT(),%s,%s)""",
                        (job["id"], game_id, owner_user_id, job.get("source_material", ""), job["id"], request_hash,
                         _json(job.get("options", {})), f"jobs/{job['id']}", hashlib.sha256(str(job.get("source_material", "")).encode("utf-8")).hexdigest()),
                    )
                    cursor.execute(
                        "INSERT INTO generation_job_events(job_id,event_type,status) VALUES(%s,'CREATED','CREATED')",
                        (job["id"],),
                    )
                connection.commit()
                job["_lock_version"] = 0
            except Exception:
                connection.rollback()
                raise

    def job_dir(self, job_id: str) -> Path:
        if not JOB_ID_RE.fullmatch(job_id):
            raise FileNotFoundError(f"job not found: {job_id}")
        return self.jobs_dir / job_id

    def job_file(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "job.json"

    def get(self, job_id: str) -> dict[str, Any]:
        if self.database_enabled:
            return self._get_database_job(job_id)
        path = self.job_file(job_id)
        if not path.exists():
            raise FileNotFoundError(f"job not found: {job_id}")
        job = read_json(path)
        self._ensure_build_metadata(job)
        return job

    def save(self, job: dict[str, Any]) -> None:
        if self.database_enabled:
            self._save_database_job(job)
            return
        self._ensure_build_metadata(job)
        job["updated_at"] = utc_now()
        write_json(self.job_file(job["id"]), job)

    def _get_database_job(self, job_id: str) -> dict[str, Any]:
        self.job_dir(job_id)
        with database_connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM generation_jobs WHERE id=%s", (job_id,))
            row = cursor.fetchone()
            if not row:
                raise FileNotFoundError(f"job not found: {job_id}")
            cursor.execute(
                "SELECT created_at,status,phase,message FROM generation_job_events WHERE job_id=%s ORDER BY id DESC LIMIT 200",
                (job_id,),
            )
            history_rows = list(reversed(cursor.fetchall()))
        return self._database_row_to_job(row, history_rows)

    def _database_row_to_job(self, row: dict[str, Any], history_rows: list[dict[str, Any]]) -> dict[str, Any]:
        legacy_status = str(row.get("legacy_status") or row["status"])
        return {
            "id": str(row["id"]), "game_id": str(row["game_id"]),
            "status": legacy_status, "phase": row.get("phase"),
            "source_material": str(row.get("source_material") or ""),
            "options": _json_value(row.get("options_json"), {}),
            "identity": {"type": "sso", "user_id": str(row["owner_user_id"])},
            "error": row.get("error_message"),
            "created_at": _iso(row.get("created_at")), "updated_at": _iso(row.get("updated_at")),
            "artifacts": _json_value(row.get("artifact_manifest_json"), {}),
            "history": [
                {"at": _iso(item.get("created_at")), "status": item.get("status"), "phase": item.get("phase"), **({"error": item["message"]} if item.get("message") else {})}
                for item in history_rows
            ],
            "draft_revision": int(row.get("draft_revision") or 0),
            "published_revision": int(row.get("published_revision") or 0),
            "build_state": str(row.get("build_state") or "NONE"),
            "dirty_scopes": _json_value(row.get("dirty_scopes"), []),
            "has_published_build": int(row.get("published_revision") or 0) > 0,
            "_lock_version": int(row.get("lock_version") or 0),
        }

    def _save_database_job(self, job: dict[str, Any], event: dict[str, Any] | None = None) -> None:
        lock_version = int(job.get("_lock_version", 0))
        legacy_status = str(job.get("status") or "CREATED")
        canonical = _canonical_status(legacy_status)
        with database_connection() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """UPDATE generation_jobs SET status=%s,legacy_status=%s,phase=%s,source_material=%s,
                        draft_revision=%s,published_revision=%s,build_state=%s,dirty_scopes=%s,options_json=%s,
                        artifact_manifest_json=%s,error_message=%s,
                        started_at=CASE WHEN %s='RUNNING' THEN COALESCE(started_at,UTC_TIMESTAMP(3)) ELSE started_at END,
                        finished_at=CASE WHEN %s IN ('SUCCEEDED','FAILED','CANCELLED') THEN UTC_TIMESTAMP(3) ELSE NULL END,
                        lock_version=lock_version+1
                        WHERE id=%s AND lock_version=%s""",
                        (canonical, legacy_status, job.get("phase"), job.get("source_material", ""),
                         int(job.get("draft_revision", 0)), int(job.get("published_revision", 0)),
                         job.get("build_state", "NONE"), _json(job.get("dirty_scopes", [])),
                         _json(job.get("options", {})), _json(job.get("artifacts", {})), job.get("error"), canonical, canonical,
                         job["id"], lock_version),
                    )
                    if cursor.rowcount != 1:
                        raise RuntimeError("job state changed concurrently; reload and retry")
                    if event:
                        cursor.execute(
                            "INSERT INTO generation_job_events(job_id,event_type,status,phase,message) VALUES(%s,%s,%s,%s,%s)",
                            (job["id"], event["event_type"], event.get("status"), event.get("phase"), event.get("message")),
                        )
                connection.commit()
                job["_lock_version"] = lock_version + 1
                job["updated_at"] = utc_now()
            except Exception:
                connection.rollback()
                raise

    def _ensure_build_metadata(self, job: dict[str, Any]) -> None:
        if self.database_enabled:
            return
        job_dir = self.job_dir(str(job["id"]))
        has_published_build = (job_dir / "public" / "game" / "config.txt").exists()
        job["has_published_build"] = has_published_build
        if "draft_revision" not in job:
            job["draft_revision"] = 1 if has_published_build else 0
        if "published_revision" not in job:
            job["published_revision"] = int(job["draft_revision"]) if has_published_build else 0
        if "build_state" not in job:
            job["build_state"] = "CURRENT" if has_published_build else "NONE"
        if not isinstance(job.get("dirty_scopes"), list):
            job["dirty_scopes"] = []

    def mark_draft_changed(self, job: dict[str, Any], scope: str) -> None:
        self._ensure_build_metadata(job)
        job["draft_revision"] = int(job.get("draft_revision", 0)) + 1
        scopes = [str(item) for item in job.get("dirty_scopes", []) if str(item)]
        if scope not in scopes:
            scopes.append(scope)
        job["dirty_scopes"] = scopes
        job["build_state"] = "STALE" if job.get("has_published_build") else "DRAFT"
        self.save(job)

    def mark_build_started(self, job: dict[str, Any]) -> None:
        job["build_state"] = "BUILDING"
        self.save(job)

    def mark_build_complete(self, job: dict[str, Any]) -> None:
        job["published_revision"] = int(job.get("draft_revision", 0))
        job["build_state"] = "CURRENT"
        job["dirty_scopes"] = []
        self.save(job)

    def mark_build_failed(self, job: dict[str, Any]) -> None:
        job["build_state"] = "FAILED"
        self.save(job)

    def transition(self, job: dict[str, Any], status: str, phase: str | None = None) -> None:
        job["status"] = status
        job["phase"] = phase
        if status != "FAILED":
            job["error"] = None
        job["history"].append({"at": utc_now(), "status": status, "phase": phase})
        if self.database_enabled:
            self._save_database_job(job, {"event_type": "STATUS", "status": status, "phase": phase})
        else:
            self.save(job)

    def set_error(self, job: dict[str, Any], message: str) -> None:
        job["status"] = "FAILED"
        job["error"] = message
        job["history"].append({"at": utc_now(), "status": "FAILED", "error": message})
        if self.database_enabled:
            self._save_database_job(job, {"event_type": "ERROR", "status": "FAILED", "phase": job.get("phase"), "message": message})
        else:
            self.save(job)

    def list(self, identity: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if not self.database_enabled:
            jobs = []
            for path in sorted(self.jobs_dir.glob("*/job.json"), key=lambda item: item.stat().st_mtime, reverse=True):
                try:
                    jobs.append(self.get(path.parent.name))
                except FileNotFoundError:
                    continue
            return jobs
        if not identity or identity.get("type") != "sso":
            return []
        with database_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM generation_jobs WHERE owner_user_id=%s ORDER BY created_at DESC,id DESC LIMIT 200",
                (identity.get("user_id"),),
            )
            rows = list(cursor.fetchall())
        return [self._database_row_to_job(row, []) for row in rows]

    def artifact_path(self, job_id: str, relative_path: str) -> Path:
        clean = relative_path.replace("\\", "/").lstrip("/")
        path = (self.job_dir(job_id) / clean).resolve()
        root = self.job_dir(job_id).resolve()
        if root != path and root not in path.parents:
            raise ValueError(f"artifact path escapes job directory: {relative_path}")
        return path

    def record_artifact(self, job: dict[str, Any], name: str, relative_path: str) -> None:
        job["artifacts"][name] = relative_path.replace("\\", "/")
        self.save(job)

    def list_artifacts(self, job_id: str) -> list[str]:
        root = self.job_dir(job_id)
        if not root.exists():
            raise FileNotFoundError(f"job not found: {job_id}")
        return [
            str(path.relative_to(root)).replace("\\", "/")
            for path in root.rglob("*")
            if path.is_file()
        ]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return str(value or "")


def _canonical_status(status: str) -> str:
    if status in {"CREATED", "QUEUED", "RUNNING", "FAILED", "CANCELLED"}:
        return status
    if status == "DONE":
        return "SUCCEEDED"
    return "WAITING_INPUT"
