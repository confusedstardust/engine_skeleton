"""Durable, private NarAgent works on the existing Forge jobs volume.

The same atomic JSON helpers and per-environment Docker volume as RPG jobs are
reused. Generated artifacts are copied from authenticated NarAgent responses
before a work enters the user's long-term library. Files are immutable by version.
"""
from __future__ import annotations

import fcntl
import re
import shutil
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path

from .config import settings
from .storage import read_json, utc_now, write_json

IDENTIFIER = re.compile(r"^[0-9a-f]{32}$")
ASSET_LIMITS = {"index.html": 2_000_000, "preview.png": 3_000_000, "mobile.png": 3_000_000}


class WorkConflictError(ValueError):
    pass


class WorkStore:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or (settings.jobs_dir / ".nar-works")).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def locked(self):
        # Linux flock works across concurrent Uvicorn worker processes.
        with (self.root / ".write.lock").open("a+") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def path(self, work_id: str) -> Path:
        if not IDENTIFIER.fullmatch(work_id):
            raise FileNotFoundError("Work not found")
        return self.root / work_id

    def get(self, owner: str, work_id: str) -> dict:
        try:
            work = read_json(self.path(work_id) / "work.json")
            if not isinstance(work, dict) or work.get("owner_user_id") != owner:
                raise FileNotFoundError("Work not found")
            return work
        except (OSError, ValueError):
            raise FileNotFoundError("Work not found") from None

    def list_for(self, owner: str) -> list[dict]:
        works = []
        for path in self.root.glob("*/work.json"):
            try:
                item = read_json(path)
                if item.get("owner_user_id") == owner:
                    works.append(item)
            except (OSError, ValueError, AttributeError):
                continue
        return sorted(works, key=lambda item: item.get("updated_at") or "", reverse=True)

    def find_by_artifact(self, owner: str, artifact_id: str) -> dict | None:
        """Resolve an already-saved immutable artifact without depending on NarAgent retention."""
        if not IDENTIFIER.fullmatch(artifact_id):
            return None
        for item in self.list_for(owner):
            if any(version["artifact_id"] == artifact_id for version in item.get("versions", [])):
                return item
        return None

    @staticmethod
    def validate_assets(assets: dict[str, bytes]):
        for filename, limit in ASSET_LIMITS.items():
            data = assets.get(filename)
            if not isinstance(data, bytes) or not data or len(data) > limit:
                raise ValueError("Invalid or oversized artifact file: " + filename)

    @staticmethod
    def _make_version(artifact_id: str, number: int) -> dict:
        return {"id": uuid.uuid4().hex, "artifact_id": artifact_id,
                "version_number": number, "created_at": utc_now()}

    def _copy_version(self, destination: Path, assets: dict[str, bytes]):
        destination.mkdir(mode=0o700, parents=True, exist_ok=False)
        for name, data in assets.items():
            if name in ASSET_LIMITS:
                path = destination / name
                path.write_bytes(data)
                path.chmod(0o600)

    def create(self, owner: str, artifact_id: str, kind: str, title: str,
               summary: str, assets: dict[str, bytes]) -> dict:
        if not IDENTIFIER.fullmatch(artifact_id) or kind not in {"html", "animation"}:
            raise ValueError("Invalid artifact ID or kind")
        self.validate_assets(assets)
        with self.locked():
            existing = self.find_by_artifact(owner, artifact_id)
            if existing:
                return existing
            work_id = uuid.uuid4().hex
            version = self._make_version(artifact_id, 1)
            now = utc_now()
            work = {
                "id": work_id, "owner_user_id": owner, "kind": kind,
                "title": title.strip()[:160] or "未命名互动作品",
                "summary": summary.strip()[:2000], "subject": None, "grade": None,
                "tags": [], "current_version_id": version["id"],
                "versions": [version], "publication_status": "draft",
                "published_version_id": None, "public_url": None, "published_at": None,
                "created_at": now, "updated_at": now, "saved_at": now,
            }
            pending = Path(tempfile.mkdtemp(prefix=".work-", dir=self.root))
            try:
                self._copy_version(pending / "versions" / version["id"], assets)
                write_json(pending / "work.json", work)
                pending.rename(self.path(work_id))
            finally:
                if pending.exists():
                    shutil.rmtree(pending)
            return work

    def add_version(self, owner: str, work_id: str, artifact_id: str,
                    assets: dict[str, bytes], expected_parent_artifact_id: str) -> dict:
        if not IDENTIFIER.fullmatch(artifact_id):
            raise ValueError("Invalid artifact ID")
        self.validate_assets(assets)
        with self.locked():
            work = self.get(owner, work_id)
            previous = next(version for version in work["versions"]
                            if version["id"] == work["current_version_id"])
            if previous["artifact_id"] != expected_parent_artifact_id:
                raise WorkConflictError("Work changed since the edited version was opened")
            for old in work["versions"]:
                if old["artifact_id"] == artifact_id:
                    return work
            version = self._make_version(artifact_id, len(work["versions"]) + 1)
            destination = self.path(work_id) / "versions" / version["id"]
            try:
                self._copy_version(destination, assets)
                work["versions"].append(version)
                work["current_version_id"] = version["id"]
                work["updated_at"] = utc_now()
                write_json(self.path(work_id) / "work.json", work)
            except BaseException:
                if destination.exists():
                    shutil.rmtree(destination)
                raise
            return work

    def update(self, owner: str, work_id: str, **fields) -> dict:
        with self.locked():
            work = self.get(owner, work_id)
            for name, value in fields.items():
                if name in {"title", "summary", "subject", "grade", "tags"}:
                    work[name] = value
            work["updated_at"] = utc_now()
            write_json(self.path(work_id) / "work.json", work)
            return work

    def asset(self, owner: str, work_id: str, version_id: str, filename: str) -> bytes:
        work = self.get(owner, work_id)
        if filename not in ASSET_LIMITS or not IDENTIFIER.fullmatch(version_id):
            raise FileNotFoundError("Work file not found")
        if not any(version["id"] == version_id for version in work["versions"]):
            raise FileNotFoundError("Work file not found")
        return (self.path(work_id) / "versions" / version_id / filename).read_bytes()

    def start_publication(self, owner: str, work_id: str) -> dict:
        """Mark pending; never switch the public version until remote publication succeeds."""
        with self.locked():
            work = self.get(owner, work_id)
            if work["kind"] != "html":
                raise WorkConflictError("Only verified interactive HTML works can be published.")
            if work.get("publication_status") in {"publishing", "unpublish_pending"}:
                raise WorkConflictError("Publication or revocation is already in progress")
            work["publication_status"] = "publishing"
            work["pending_version_id"] = work["current_version_id"]
            work["updated_at"] = utc_now()
            write_json(self.path(work_id) / "work.json", work)
            return work

    def finish_publication(self, owner: str, work_id: str, version_id: str, public_url: str, snapshot: dict) -> dict:
        with self.locked():
            work = self.get(owner, work_id)
            if (work.get("publication_status") != "publishing" or
                    work.get("pending_version_id") != version_id):
                raise WorkConflictError("Publication state changed during upload")
            work["publication_status"] = "published"
            work["published_version_id"] = version_id
            work["published_at"] = utc_now()
            work["public_url"] = public_url
            work["published_metadata"] = {key: snapshot.get(key) for key in ("title", "summary", "subject", "grade", "tags")}
            # The publish-dialog metadata is also the user's saved work metadata.
            work.update(work["published_metadata"])
            work.pop("pending_version_id", None)
            work["updated_at"] = utc_now()
            write_json(self.path(work_id) / "work.json", work)
            return work

    def rollback_publication(self, owner: str, work_id: str):
        with self.locked():
            work = self.get(owner, work_id)
            if work.get("publication_status") == "publishing":
                work["publication_status"] = "published" if work.get("published_version_id") else "failed"
                work.pop("pending_version_id", None)
                work["updated_at"] = utc_now()
                write_json(self.path(work_id) / "work.json", work)

    def start_unpublish(self, owner: str, work_id: str) -> dict:
        """Immediately revoke public access, even if remote de-indexing fails."""
        with self.locked():
            work = self.get(owner, work_id)
            if not work.get("published_version_id") or work.get("publication_status") not in {"published", "unpublish_pending"}:
                raise WorkConflictError("Work has no currently revocable publication")
            work["publication_status"] = "unpublish_pending"
            work["updated_at"] = utc_now()
            write_json(self.path(work_id) / "work.json", work)
            return work

    def finish_unpublish(self, owner: str, work_id: str) -> dict:
        with self.locked():
            work = self.get(owner, work_id)
            if work.get("publication_status") != "unpublish_pending":
                raise WorkConflictError("Publication state changed before revocation completed")
            work["publication_status"] = "unpublished"
            work["published_version_id"] = None
            work["public_url"] = None
            work.pop("pending_version_id", None)
            work["updated_at"] = utc_now()
            write_json(self.path(work_id) / "work.json", work)
            return work

    def public(self, work_id: str) -> dict:
        """Published metadata only; never return drafts, user IDs or source paths."""
        try:
            path = self.path(work_id)
            work = read_json(path / "work.json")
        except (OSError, ValueError):
            raise FileNotFoundError("Public work not found") from None
        if (not isinstance(work, dict) or work.get("publication_status") not in {"published", "publishing"} or
                not work.get("published_version_id")):
            raise FileNotFoundError("Public work not found")
        version = next((item for item in work["versions"]
                        if item["id"] == work["published_version_id"]), None)
        if not version:
            raise FileNotFoundError("Public work not found")
        return {
            "id": work_id,
            "title": (work.get("published_metadata") or {}).get("title", work["title"]),
            "summary": (work.get("published_metadata") or {}).get("summary", work.get("summary", "")),
            "kind": work["kind"],
            "subject": (work.get("published_metadata") or {}).get("subject", work.get("subject")),
            "grade": (work.get("published_metadata") or {}).get("grade", work.get("grade")),
            "tags": (work.get("published_metadata") or {}).get("tags", work.get("tags", [])),
            "published_at": work.get("published_at"),
            "version": version["version_number"], "published_version_id": version["id"],
        }

    def public_asset(self, work_id: str, filename: str) -> bytes:
        meta = self.public(work_id)
        if filename not in ASSET_LIMITS:
            raise FileNotFoundError("Public work file not found")
        return (self.path(work_id) / "versions" / meta["published_version_id"] / filename).read_bytes()
