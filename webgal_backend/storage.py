from __future__ import annotations

import json
import hashlib
import logging
import os
import re
import sqlite3
import tempfile
import time
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from .config import settings


JOB_ID_RE = re.compile(r"^[a-f0-9]{32}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_bytes_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def write_text_atomic(path: Path, content: str) -> None:
    write_bytes_atomic(path, content.encode("utf-8"))


def write_json(path: Path, data: Any) -> None:
    write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


class JobBusyError(RuntimeError):
    pass


class ConcurrentJobUpdateError(RuntimeError):
    pass


ARTIFACT_DEPENDENCIES: dict[str, set[str]] = {
    "scene_plan": {"narrative_plan"},
    "game_design": {"narrative_plan", "scene_plan"},
    "game_design_outline": {"game_design", "scene_plan"},
    "game_design_choices": {"game_design", "game_design_outline"},
    "game_project": {"game_design", "game_design_choices"},
    "game_design_completed": {"game_project"},
    "asset_manifest": {"narrative_plan", "game_project"},
    "script_assets": {"asset_manifest", "game_project"},
    "script_asset_operations": {"asset_manifest", "game_project"},
    "game_design_webgal": {"game_project", "script_assets", "script_asset_operations"},
    "sound_effect_plan": {"game_design_webgal"},
    "bgm_plan": {"game_design_webgal"},
    "tts_manifest": {"narrative_plan", "game_design_webgal"},
    "scene_files": {"game_design_webgal"},
    "repair_report": {"scene_files"},
    "validation_report": {"scene_files", "repair_report"},
    "published_revision": {"validation_report"},
}
TRACKED_ARTIFACTS = set(ARTIFACT_DEPENDENCIES) | {
    dependency for dependencies in ARTIFACT_DEPENDENCIES.values() for dependency in dependencies
}


def _artifact_descendants(name: str) -> set[str]:
    descendants: set[str] = set()
    frontier = [name]
    while frontier:
        parent = frontier.pop()
        for candidate, dependencies in ARTIFACT_DEPENDENCIES.items():
            if parent in dependencies and candidate not in descendants:
                descendants.add(candidate)
                frontier.append(candidate)
    return descendants


def _file_digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _process_exists(pid: Any) -> bool:
    try:
        process_id = int(pid)
    except (TypeError, ValueError):
        return False
    if process_id <= 0:
        return False
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


class JobStore:
    def __init__(self, jobs_dir: Path | None = None) -> None:
        self.jobs_dir = jobs_dir or settings.jobs_dir
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.database_path = self.jobs_dir / "jobs.sqlite3"
        self._process_lock = RLock()
        self._initialize_database()
        self._migrate_legacy_jobs()
        self.repair_compatibility_mirrors()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _initialize_database(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    state_version INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_jobs_updated_at ON jobs(updated_at DESC)")
            connection.commit()

    def _migrate_legacy_jobs(self) -> None:
        legacy_jobs: list[dict[str, Any]] = []
        for path in self.jobs_dir.glob("*/job.json"):
            try:
                payload = read_json(path)
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict) and JOB_ID_RE.fullmatch(str(payload.get("id") or "")):
                legacy_jobs.append(payload)
        if not legacy_jobs:
            return
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            for payload in legacy_jobs:
                created_at = str(payload.get("created_at") or utc_now())
                updated_at = str(payload.get("updated_at") or created_at)
                try:
                    state_version = max(0, int(payload.get("state_version", 0)))
                except (TypeError, ValueError):
                    state_version = 0
                payload["state_version"] = state_version
                connection.execute(
                    """
                    INSERT OR IGNORE INTO jobs(id, payload_json, state_version, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        payload["id"],
                        json.dumps(payload, ensure_ascii=False),
                        state_version,
                        created_at,
                        updated_at,
                    ),
                )
            connection.commit()

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
            "artifact_meta": {},
            "revision": 0,
            "publication_required": True,
            "history": [],
        }
        self.save(job)
        return job

    def job_dir(self, job_id: str) -> Path:
        if not JOB_ID_RE.fullmatch(job_id):
            raise FileNotFoundError(f"job not found: {job_id}")
        return self.jobs_dir / job_id

    def job_file(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "job.json"

    def get(self, job_id: str) -> dict[str, Any]:
        path = self.job_file(job_id)
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT payload_json FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is not None:
            return json.loads(row["payload_json"])
        if path.exists():
            legacy = read_json(path)
            self.save(legacy)
            return legacy
        raise FileNotFoundError(f"job not found: {job_id}")

    def save(self, job: dict[str, Any]) -> None:
        with self._process_lock:
            path = self.job_file(job["id"])
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    row = connection.execute(
                        "SELECT payload_json, state_version FROM jobs WHERE id = ?", (job["id"],)
                    ).fetchone()
                    if row is not None and job.get("state_version") is not None:
                        try:
                            incoming_version = int(job["state_version"])
                        except (TypeError, ValueError) as exc:
                            raise ConcurrentJobUpdateError(
                                f"invalid state_version for job {job['id']}: {job.get('state_version')}"
                            ) from exc
                        if incoming_version != int(row["state_version"]):
                            raise ConcurrentJobUpdateError(
                                f"job {job['id']} changed concurrently: expected state_version "
                                f"{incoming_version}, current state_version {row['state_version']}"
                            )
                    current = json.loads(row["payload_json"]) if row is not None else {}
                    merged = dict(current)
                    merged.update(job)
                    merged["artifacts"] = {**current.get("artifacts", {}), **job.get("artifacts", {})}
                    merged["artifact_meta"] = {**current.get("artifact_meta", {}), **job.get("artifact_meta", {})}
                    merged["history"] = self._merge_history(current.get("history", []), job.get("history", []))
                    merged["updated_at"] = utc_now()
                    merged["created_at"] = str(merged.get("created_at") or merged["updated_at"])
                    merged["state_version"] = (int(row["state_version"]) if row is not None else 0) + 1
                    payload_json = json.dumps(merged, ensure_ascii=False)
                    connection.execute(
                        """
                        INSERT INTO jobs(id, payload_json, state_version, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            payload_json = excluded.payload_json,
                            state_version = excluded.state_version,
                            created_at = excluded.created_at,
                            updated_at = excluded.updated_at
                        """,
                        (
                            merged["id"],
                            payload_json,
                            merged["state_version"],
                            merged["created_at"],
                            merged["updated_at"],
                        ),
                    )
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
            try:
                write_json(path, merged)
            except OSError as exc:
                logging.getLogger(__name__).warning(
                    "Job state committed to SQLite but compatibility mirror could not be updated: job_id=%s path=%s error=%s",
                    job["id"],
                    path,
                    exc,
                )
            job.clear()
            job.update(merged)

    def list_all(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT payload_json FROM jobs ORDER BY updated_at DESC").fetchall()
        jobs: list[dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                jobs.append(payload)
        return jobs

    def repair_compatibility_mirrors(self) -> dict[str, int]:
        result = {"checked": 0, "repaired": 0, "failed": 0}
        for job in self.list_all():
            result["checked"] += 1
            path = self.job_file(job["id"])
            try:
                mirror = read_json(path) if path.exists() else None
                if (
                    isinstance(mirror, dict)
                    and mirror.get("id") == job["id"]
                    and mirror.get("state_version") == job.get("state_version")
                ):
                    continue
                write_json(path, job)
                result["repaired"] += 1
            except (OSError, json.JSONDecodeError) as exc:
                result["failed"] += 1
                logging.getLogger(__name__).warning(
                    "Could not repair job compatibility mirror: job_id=%s path=%s error=%s",
                    job["id"],
                    path,
                    exc,
                )
        return result

    def transition(self, job: dict[str, Any], status: str, phase: str | None = None) -> None:
        with self._process_lock:
            current = self.get(job["id"])
            current["status"] = status
            current["phase"] = phase
            if status != "FAILED":
                current["error"] = None
            current.setdefault("history", []).append({"at": utc_now(), "status": status, "phase": phase})
            self.save(current)
            job.clear()
            job.update(current)

    def set_error(self, job: dict[str, Any], message: str) -> None:
        with self._process_lock:
            current = self.get(job["id"])
            current["status"] = "FAILED"
            current["error"] = message
            current.setdefault("history", []).append({"at": utc_now(), "status": "FAILED", "error": message})
            self.save(current)
            job.clear()
            job.update(current)

    def artifact_path(self, job_id: str, relative_path: str) -> Path:
        clean = relative_path.replace("\\", "/").lstrip("/")
        path = (self.job_dir(job_id) / clean).resolve()
        root = self.job_dir(job_id).resolve()
        if root != path and root not in path.parents:
            raise ValueError(f"artifact path escapes job directory: {relative_path}")
        return path

    def record_artifact(self, job: dict[str, Any], name: str, relative_path: str) -> None:
        normalized_path = relative_path.replace("\\", "/")
        with self._process_lock:
            current = self.get(job["id"])
            metadata = current.setdefault("artifact_meta", {})
            previous = metadata.get(name, {})
            digest = _file_digest(self.artifact_path(job["id"], normalized_path))
            changed = name in TRACKED_ARTIFACTS and digest is not None and digest != previous.get("sha256")
            if changed:
                current["revision"] = int(current.get("revision", 0)) + 1
                for descendant in _artifact_descendants(name):
                    if descendant in metadata:
                        metadata[descendant]["status"] = "stale"
                        metadata[descendant]["stale_because"] = name
            input_hashes = {
                dependency: metadata.get(dependency, {}).get("sha256")
                for dependency in sorted(ARTIFACT_DEPENDENCIES.get(name, set()))
            }
            metadata[name] = {
                "path": normalized_path,
                "sha256": digest,
                "revision": int(current.get("revision", 0)),
                "status": "fresh",
                "input_hashes": input_hashes,
                "updated_at": utc_now(),
            }
            current.setdefault("artifacts", {})[name] = normalized_path
            self.save(current)
            job.clear()
            job.update(current)

    def reserve_execution(self, job_id: str, *, stale_after_seconds: int = 6 * 60 * 60) -> str:
        lock_path = self.job_dir(job_id) / ".run.lock"
        token = uuid.uuid4().hex
        if lock_path.exists():
            try:
                lock_data = read_json(lock_path)
            except (OSError, json.JSONDecodeError):
                lock_data = {}
            lock_expired = time.time() - lock_path.stat().st_mtime > stale_after_seconds
            owner_pid = lock_data.get("pid")
            if (owner_pid and not _process_exists(owner_pid)) or (not owner_pid and lock_expired):
                lock_path.unlink(missing_ok=True)
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise JobBusyError(f"job is already queued or running: {job_id}") from exc
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"token": token, "pid": os.getpid(), "created_at": utc_now()}))
        return token

    def is_execution_active(self, job_id: str) -> bool:
        return (self.job_dir(job_id) / ".run.lock").exists()

    def require_artifacts_fresh(self, job_id: str, names: set[str]) -> None:
        job = self.get(job_id)
        metadata = job.get("artifact_meta", {})
        stale = sorted(name for name in names if metadata.get(name, {}).get("status") == "stale")
        if stale:
            raise ValueError("stale prerequisite artifacts must be regenerated: " + ", ".join(stale))

    def mark_artifacts_stale(self, job: dict[str, Any], names: set[str], *, because: str) -> None:
        with self._process_lock:
            current = self.get(job["id"])
            metadata = current.setdefault("artifact_meta", {})
            for name in names:
                if name in metadata:
                    metadata[name]["status"] = "stale"
                    metadata[name]["stale_because"] = because
            self.save(current)
            job.clear()
            job.update(current)

    @contextmanager
    def execution(self, job_id: str, token: str | None = None):
        lock_path = self.job_dir(job_id) / ".run.lock"
        owner_token = token or self.reserve_execution(job_id)
        if token:
            try:
                lock_data = read_json(lock_path)
            except (FileNotFoundError, json.JSONDecodeError) as exc:
                raise JobBusyError(f"job execution reservation was lost: {job_id}") from exc
            if lock_data.get("token") != token:
                raise JobBusyError(f"job execution reservation belongs to another runner: {job_id}")
        try:
            yield owner_token
        finally:
            try:
                lock_data = read_json(lock_path)
            except (FileNotFoundError, json.JSONDecodeError):
                lock_data = {}
            if lock_data.get("token") == owner_token:
                lock_path.unlink(missing_ok=True)

    def recover_stale_running_jobs(self, *, protected_job_ids: set[str] | None = None) -> int:
        recovered = 0
        protected_job_ids = protected_job_ids or set()
        for job in self.list_all():
            if job.get("status") not in {"RUNNING", "QUEUED"}:
                continue
            if str(job.get("id") or "") in protected_job_ids:
                continue
            lock_path = self.job_dir(job["id"]) / ".run.lock"
            if lock_path.exists():
                try:
                    lock_data = read_json(lock_path)
                except (OSError, json.JSONDecodeError):
                    lock_data = {}
                if _process_exists(lock_data.get("pid")):
                    continue
                lock_path.unlink(missing_ok=True)
            self.set_error(job, "generation interrupted before completion; rerun the failed phase")
            job["active_run_id"] = None
            self.save(job)
            recovered += 1
        return recovered

    def clear_inactive_run_reservations(self, active_run_ids: set[str]) -> int:
        cleared = 0
        for job in self.list_all():
            run_id = str(job.get("active_run_id") or "")
            if not run_id or run_id in active_run_ids:
                continue
            if job.get("status") in {"RUNNING", "QUEUED"}:
                self.set_error(job, "task reservation ended before job state was finalized; rerun the interrupted phase")
            job["active_run_id"] = None
            job.setdefault("history", []).append(
                {"at": utc_now(), "status": job.get("status"), "event": "STALE_RUN_RESERVATION_CLEARED", "run_id": run_id}
            )
            self.save(job)
            cleared += 1
        return cleared

    @staticmethod
    def _merge_history(current: list[Any], incoming: list[Any]) -> list[Any]:
        result: list[Any] = []
        seen: set[str] = set()
        for event in [*current, *incoming]:
            marker = json.dumps(event, ensure_ascii=False, sort_keys=True)
            if marker not in seen:
                seen.add(marker)
                result.append(event)
        return result

    def list_artifacts(self, job_id: str) -> list[str]:
        root = self.job_dir(job_id)
        if not root.exists():
            raise FileNotFoundError(f"job not found: {job_id}")
        return [
            str(path.relative_to(root)).replace("\\", "/")
            for path in root.rglob("*")
            if path.is_file()
        ]
