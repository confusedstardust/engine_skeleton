from __future__ import annotations

import hashlib
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from .storage import read_json, utc_now, write_json


REVISION_RE = re.compile(r"^r[0-9]{6,}-[a-f0-9]{12}$")


class PublishError(RuntimeError):
    pass


def publish_game_revision(job_dir: Path, *, source_revision: int) -> dict[str, Any]:
    source_public = job_dir / "public"
    source_game = source_public / "game"
    _validate_publish_source(source_game)
    source_manifest = _directory_manifest(source_public)
    root_hash = _manifest_hash(source_manifest)
    revision_id = f"r{max(0, int(source_revision)):06d}-{root_hash[:12]}"

    revisions_dir = job_dir / "revisions"
    revisions_dir.mkdir(parents=True, exist_ok=True)
    final_dir = revisions_dir / revision_id
    if not final_dir.exists():
        staging_dir = revisions_dir / f".staging-{uuid.uuid4().hex}"
        try:
            shutil.copytree(source_public, staging_dir / "public")
            copied_manifest = _directory_manifest(staging_dir / "public")
            if copied_manifest != source_manifest:
                raise PublishError("published snapshot verification failed: source changed during copy")
            manifest = {
                "version": 1,
                "revision_id": revision_id,
                "source_revision": int(source_revision),
                "root_hash": root_hash,
                "created_at": utc_now(),
                "files": copied_manifest,
            }
            write_json(staging_dir / "manifest.json", manifest)
            try:
                os.replace(staging_dir, final_dir)
            except FileExistsError:
                _safe_rmtree(staging_dir, revisions_dir)
        except Exception:
            _safe_rmtree(staging_dir, revisions_dir)
            raise
    else:
        manifest = read_json(final_dir / "manifest.json")
        if manifest.get("root_hash") != root_hash:
            raise PublishError(f"revision collision detected: {revision_id}")

    pointer = {
        "version": 1,
        "revision_id": revision_id,
        "source_revision": int(source_revision),
        "root_hash": root_hash,
        "published_at": utc_now(),
        "manifest": f"revisions/{revision_id}/manifest.json",
        "public_root": f"revisions/{revision_id}/public",
    }
    write_json(job_dir / "state" / "published_revision.json", pointer)
    return pointer


def published_game_root(job_dir: Path, *, fallback_to_working: bool = True) -> Path | None:
    pointer_path = job_dir / "state" / "published_revision.json"
    if pointer_path.exists():
        try:
            pointer = read_json(pointer_path)
        except Exception:
            pointer = {}
        revision_id = str(pointer.get("revision_id") or "")
        if REVISION_RE.fullmatch(revision_id):
            candidate = job_dir / "revisions" / revision_id / "public" / "game"
            if candidate.is_dir():
                return candidate
    working = job_dir / "public" / "game"
    if fallback_to_working and working.is_dir():
        return working
    return None


def current_publication(job_dir: Path) -> dict[str, Any] | None:
    pointer_path = job_dir / "state" / "published_revision.json"
    if not pointer_path.exists():
        return None
    try:
        pointer = read_json(pointer_path)
    except Exception:
        return None
    revision_id = str(pointer.get("revision_id") or "")
    if not REVISION_RE.fullmatch(revision_id):
        return None
    if not (job_dir / "revisions" / revision_id / "manifest.json").is_file():
        return None
    return pointer


def list_game_revisions(job_dir: Path) -> list[dict[str, Any]]:
    current = current_publication(job_dir)
    current_id = str(current.get("revision_id") or "") if current else ""
    revisions_dir = job_dir / "revisions"
    revisions: list[dict[str, Any]] = []
    if not revisions_dir.is_dir():
        return revisions
    for revision_dir in revisions_dir.iterdir():
        if not revision_dir.is_dir() or not REVISION_RE.fullmatch(revision_dir.name):
            continue
        try:
            manifest = read_json(revision_dir / "manifest.json")
        except Exception:
            continue
        if manifest.get("revision_id") != revision_dir.name:
            continue
        revisions.append(
            {
                "revision_id": revision_dir.name,
                "source_revision": manifest.get("source_revision"),
                "root_hash": manifest.get("root_hash"),
                "created_at": manifest.get("created_at"),
                "file_count": len(manifest.get("files", [])),
                "is_current": revision_dir.name == current_id,
            }
        )
    return sorted(
        revisions,
        key=lambda item: (str(item.get("created_at") or ""), str(item["revision_id"])),
        reverse=True,
    )


def activate_game_revision(job_dir: Path, revision_id: str) -> dict[str, Any]:
    if not REVISION_RE.fullmatch(revision_id):
        raise PublishError(f"invalid publication revision: {revision_id}")
    revision_dir = job_dir / "revisions" / revision_id
    manifest_path = revision_dir / "manifest.json"
    public_root = revision_dir / "public"
    if not manifest_path.is_file() or not public_root.is_dir():
        raise PublishError(f"publication revision does not exist: {revision_id}")
    try:
        manifest = read_json(manifest_path)
    except Exception as exc:
        raise PublishError(f"publication manifest cannot be read: {revision_id}") from exc
    if manifest.get("revision_id") != revision_id:
        raise PublishError(f"publication manifest revision mismatch: {revision_id}")
    expected_files = manifest.get("files")
    expected_hash = str(manifest.get("root_hash") or "")
    if not isinstance(expected_files, list) or not expected_hash:
        raise PublishError(f"publication manifest is incomplete: {revision_id}")
    actual_files = _directory_manifest(public_root)
    actual_hash = _manifest_hash(actual_files)
    if actual_files != expected_files or actual_hash != expected_hash:
        raise PublishError(f"publication revision failed integrity verification: {revision_id}")
    _validate_publish_source(public_root / "game")

    pointer = {
        "version": 1,
        "revision_id": revision_id,
        "source_revision": manifest.get("source_revision"),
        "root_hash": expected_hash,
        "published_at": utc_now(),
        "manifest": f"revisions/{revision_id}/manifest.json",
        "public_root": f"revisions/{revision_id}/public",
    }
    write_json(job_dir / "state" / "published_revision.json", pointer)
    return pointer


def revision_game_root(job_dir: Path, revision_id: str) -> Path | None:
    if not REVISION_RE.fullmatch(revision_id):
        return None
    candidate = job_dir / "revisions" / revision_id / "public" / "game"
    return candidate if candidate.is_dir() else None


def _validate_publish_source(source_game: Path) -> None:
    if not source_game.is_dir():
        raise PublishError("public/game does not exist")
    scene_dir = source_game / "scene"
    if not (scene_dir / "start.txt").is_file():
        raise PublishError("public/game/scene/start.txt is required for publishing")
    if not list(scene_dir.glob("*.txt")):
        raise PublishError("no scene files are available for publishing")
    if not (source_game / "config.txt").is_file():
        raise PublishError("public/game/config.txt is required for publishing")


def _directory_manifest(root: Path) -> list[dict[str, Any]]:
    files = []
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        files.append({"path": relative, "size": path.stat().st_size, "sha256": digest.hexdigest()})
    return files


def _manifest_hash(files: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for item in files:
        digest.update(str(item["path"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(item["size"]).encode("ascii"))
        digest.update(b"\0")
        digest.update(str(item["sha256"]).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _safe_rmtree(path: Path, expected_parent: Path) -> None:
    if not path.exists():
        return
    resolved = path.resolve()
    parent = expected_parent.resolve()
    if resolved.parent != parent or not resolved.name.startswith(".staging-"):
        raise PublishError(f"refusing to remove unexpected staging path: {resolved}")
    shutil.rmtree(resolved)
