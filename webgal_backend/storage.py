from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import settings


JOB_ID_RE = re.compile(r"^[a-f0-9]{32}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class JobStore:
    def __init__(self, jobs_dir: Path | None = None) -> None:
        self.jobs_dir = jobs_dir or settings.jobs_dir
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    def create(self, source_material: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
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
            "error": None,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "artifacts": {},
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
        if not path.exists():
            raise FileNotFoundError(f"job not found: {job_id}")
        return read_json(path)

    def save(self, job: dict[str, Any]) -> None:
        job["updated_at"] = utc_now()
        write_json(self.job_file(job["id"]), job)

    def transition(self, job: dict[str, Any], status: str, phase: str | None = None) -> None:
        job["status"] = status
        job["phase"] = phase
        if status != "FAILED":
            job["error"] = None
        job["history"].append({"at": utc_now(), "status": status, "phase": phase})
        self.save(job)

    def set_error(self, job: dict[str, Any], message: str) -> None:
        job["status"] = "FAILED"
        job["error"] = message
        job["history"].append({"at": utc_now(), "status": "FAILED", "error": message})
        self.save(job)

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
