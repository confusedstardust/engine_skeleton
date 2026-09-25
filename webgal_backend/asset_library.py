from __future__ import annotations

import hashlib
import mimetypes
import re
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlsplit

from .config import settings
from .database import DatabaseUnavailable, database_connection
from .oss_storage import OSSUploadError, asset_access_url, asset_object_key, upload_asset_file


class AssetLibraryError(RuntimeError):
    pass


class AssetLibraryUnavailable(AssetLibraryError):
    pass


KIND_BY_DIR = {
    "background": "BACKGROUND",
    "figure": "FIGURE",
    "vocal": "VOICE",
    "bgm": "BGM",
    "soundeffect": "SFX",
}


@dataclass(frozen=True)
class AssetFileRecord:
    asset_id: str
    file_id: str
    revision: int
    object_key: str
    url: str
    sha256: str


@contextmanager
def _connection() -> Iterator[Any]:
    if not settings.asset_library_enabled:
        raise AssetLibraryUnavailable("asset library is disabled; set WEBGAL_ASSET_LIBRARY_ENABLED=true")
    try:
        with database_connection() as connection:
            yield connection
    except DatabaseUnavailable as exc:
        raise AssetLibraryUnavailable(str(exc)) from exc


def _asset_user_id(job: dict[str, Any]) -> str | None:
    identity = job.get("identity")
    if isinstance(identity, dict) and identity.get("type") == "sso":
        user_id = str(identity.get("user_id") or "").strip()
        return user_id or None
    return None


def _file_dimensions(path: Path) -> tuple[int | None, int | None]:
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        return None, None


def _signed_url(object_key: str) -> str:
    try:
        return asset_access_url(object_key)
    except OSSUploadError as exc:
        raise AssetLibraryError(str(exc)) from exc
    try:
        from PIL import Image
        with Image.open(path) as image:
            return image.width, image.height
    except Exception:
        return None, None


class AssetLibrary:
    def enabled_for(self, job: dict[str, Any]) -> bool:
        return bool(settings.asset_library_enabled and settings.database_url and _asset_user_id(job))

    def register_file(
        self,
        *,
        user_id: str,
        job_id: str,
        source_type: str,
        kind: str,
        source_key: str,
        display_name: str,
        path: Path,
        variant: str = "original",
        generation_metadata: dict[str, Any] | None = None,
    ) -> AssetFileRecord:
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        extension = path.suffix.lower().lstrip(".") or "bin"
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        width, height = _file_dimensions(path)
        asset_id = ""
        file_id = uuid.uuid4().hex
        revision = 1

        with _connection() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT id FROM users WHERE id=%s", (user_id,))
                    if not cursor.fetchone():
                        raise AssetLibraryError("logged-in user is not present in the NarrativeOS database")
                    cursor.execute(
                        "SELECT id FROM generation_jobs WHERE id=%s AND owner_user_id=%s",
                        (job_id, user_id),
                    )
                    source_job_id = job_id if cursor.fetchone() else None
                    namespaced_source_key = f"{job_id}/{source_key.lstrip('/')}"
                    cursor.execute(
                        "SELECT id FROM assets WHERE owner_user_id=%s AND source_type=%s AND source_key=%s FOR UPDATE",
                        (user_id, source_type, namespaced_source_key),
                    )
                    row = cursor.fetchone()
                    if row:
                        asset_id = str(row["id"])
                    else:
                        asset_id = uuid.uuid4().hex
                        cursor.execute(
                            """INSERT INTO assets
                            (id,owner_user_id,source_job_id,source_key,name,kind,source_type,visibility,status,generation_metadata)
                            VALUES(%s,%s,%s,%s,%s,%s,%s,'PRIVATE','ACTIVE',%s)""",
                            (asset_id, user_id, source_job_id, namespaced_source_key, display_name, kind, source_type, _json(generation_metadata)),
                        )
                    cursor.execute(
                        "SELECT id,revision,sha256,object_key FROM asset_files "
                        "WHERE asset_id=%s AND variant=%s AND status='READY' ORDER BY revision DESC LIMIT 1",
                        (asset_id, variant),
                    )
                    existing = cursor.fetchone()
                    if existing and existing.get("sha256") == digest:
                        connection.rollback()
                        return AssetFileRecord(
                            asset_id=asset_id,
                            file_id=str(existing["id"]),
                            revision=int(existing["revision"]),
                            object_key=str(existing["object_key"]),
                            url=_signed_url(str(existing["object_key"])),
                            sha256=digest,
                        )
                    revision = int(existing["revision"]) + 1 if existing else 1
                    object_key = asset_object_key(
                        user_id=user_id,
                        source_type=source_type,
                        asset_id=asset_id,
                        revision=revision,
                        file_id=file_id,
                        extension=extension,
                    )
                    location_hash = hashlib.sha256(
                        _json(["OSS", settings.oss_bucket or "", object_key, ""]).encode("utf-8")
                    ).digest()
                    cursor.execute(
                        """INSERT INTO asset_files
                        (id,asset_id,revision,variant,storage_provider,bucket,region,object_key,location_hash,
                         sha256,mime_type,size_bytes,width_px,height_px,status)
                        VALUES(%s,%s,%s,%s,'OSS',%s,%s,%s,%s,%s,%s,%s,%s,%s,'UPLOADING')""",
                        (file_id, asset_id, revision, variant, settings.oss_bucket or "", _oss_region(), object_key,
                         location_hash, digest, mime_type, len(content), width, height),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

        try:
            stored = upload_asset_file(object_key=object_key, content=content, content_type=mime_type)
        except Exception as exc:
            self._mark_file_failed(file_id)
            raise AssetLibraryError(str(exc)) from exc

        with _connection() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE asset_files SET status='READY',etag=%s,uploaded_at=UTC_TIMESTAMP(3) "
                        "WHERE id=%s AND status='UPLOADING'",
                        (stored.etag, file_id),
                    )
                    if cursor.rowcount != 1:
                        raise AssetLibraryError("asset file state changed before upload completed")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return AssetFileRecord(asset_id, file_id, revision, stored.object_key, _signed_url(stored.object_key), digest)

    def _mark_file_failed(self, file_id: str) -> None:
        try:
            with _connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("UPDATE asset_files SET status='FAILED' WHERE id=%s AND status='UPLOADING'", (file_id,))
                connection.commit()
        except Exception:
            pass

    def list_assets(
        self, *, user_id: str, source_type: str | None = None, kind: str | None = None,
        cursor_created_at: str | None = None, cursor_id: str | None = None, limit: int = 30,
    ) -> dict[str, Any]:
        where = ["a.owner_user_id=%s", "a.status='ACTIVE'"]
        params: list[Any] = [user_id]
        if source_type:
            where.append("a.source_type=%s")
            params.append(source_type)
        if kind:
            where.append("a.kind=%s")
            params.append(kind)
        if cursor_created_at and cursor_id:
            where.append("(a.created_at<%s OR (a.created_at=%s AND a.id<%s))")
            params.extend([cursor_created_at, cursor_created_at, cursor_id])
        params.append(max(1, min(limit, 50)) + 1)
        query = f"""SELECT a.id,a.name,a.kind,a.source_type,a.visibility,a.status,a.created_at,a.updated_at,
            f.id file_id,f.revision,f.variant,f.mime_type,f.size_bytes,f.width_px,f.height_px,f.object_key
            FROM assets a
            LEFT JOIN asset_files f ON f.id=(SELECT af.id FROM asset_files af
                WHERE af.asset_id=a.id AND af.variant='original' AND af.status='READY'
                ORDER BY af.revision DESC LIMIT 1)
            WHERE {' AND '.join(where)} ORDER BY a.created_at DESC,a.id DESC LIMIT %s"""
        with _connection() as connection, connection.cursor() as db_cursor:
            db_cursor.execute(query, params)
            rows = list(db_cursor.fetchall())
        has_more = len(rows) > min(limit, 50)
        rows = rows[: min(limit, 50)]
        for row in rows:
            row["url"] = _signed_url(str(row["object_key"])) if row.get("object_key") else None
            row.pop("object_key", None)
            for key in ("created_at", "updated_at"):
                if row.get(key):
                    row[key] = row[key].isoformat()
        last = rows[-1] if has_more and rows else None
        return {"items": rows, "next_cursor": {"created_at": last["created_at"], "id": last["id"]} if last else None}

    def signed_file_url(self, *, user_id: str, file_id: str) -> str:
        with _connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT f.object_key FROM asset_files f JOIN assets a ON a.id=f.asset_id "
                "WHERE f.id=%s AND a.owner_user_id=%s AND a.status='ACTIVE' AND f.status='READY'",
                (file_id, user_id),
            )
            row = cursor.fetchone()
        if not row:
            raise FileNotFoundError("asset file not found")
        return _signed_url(str(row["object_key"]))


def _json(value: Any) -> str:
    import json
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _oss_region() -> str | None:
    host = urlsplit(settings.oss_endpoint).netloc or urlsplit(settings.oss_endpoint).path
    return host.removeprefix("oss-").split(".", 1)[0] if host.startswith("oss-") else None


asset_library = AssetLibrary()


def sync_generated_job_assets(job: dict[str, Any], job_dir: Path) -> list[dict[str, Any]]:
    if not asset_library.enabled_for(job):
        return []
    user_id = _asset_user_id(job)
    if not user_id:
        return []
    manifest_path = job_dir / "assets_manifest.json"
    manifest = {}
    if manifest_path.exists():
        import json
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    metadata_by_path: dict[str, dict[str, Any]] = {}
    for item in manifest.get("images", []) if isinstance(manifest, dict) else []:
        if not isinstance(item, dict):
            continue
        subdir = str(item.get("subdir") or "")
        name = str(item.get("filename") or "").removesuffix(".webp")
        if name:
            metadata_by_path[f"{subdir}/{name}.webp"] = item
    uploaded_paths: set[str] = set()
    uploaded_state = job_dir / "state" / "uploaded_assets.json"
    if uploaded_state.exists():
        import json
        payload = json.loads(uploaded_state.read_text(encoding="utf-8"))
        for item in payload.get("items", []) if isinstance(payload, dict) else []:
            if not isinstance(item, dict):
                continue
            category = str(item.get("subdir") or ("bgm" if item.get("type") == "bgm" else ""))
            filename = Path(str(item.get("filename") or "")).name
            if category and filename:
                uploaded_paths.add(f"{category}/{filename}")
                if category == "figure":
                    stem = Path(filename).stem
                    avatar = f"miniavatar_{stem.removeprefix('figure_')}.webp" if stem.startswith("figure_") else f"miniavatar_{stem}.webp"
                    uploaded_paths.add(f"figure/{avatar}")
    result: list[dict[str, Any]] = []
    files: dict[str, tuple[Path, str]] = {}
    for game_root in (job_dir / "public" / "game", job_dir / "draft" / "game"):
        for subdir, kind in KIND_BY_DIR.items():
            directory = game_root / subdir
            if directory.exists():
                for path in sorted(item for item in directory.iterdir() if item.is_file()):
                    files[f"{subdir}/{path.name}"] = (path, kind)
    for relative, (path, kind) in files.items():
        info = metadata_by_path.get(relative, {})
        record = asset_library.register_file(
            user_id=user_id,
            job_id=str(job["id"]),
            source_type="UPLOADED" if relative in uploaded_paths else "GENERATED",
            kind=kind,
            source_key=relative,
            display_name=str(info.get("display_name") or path.stem),
            path=path,
            generation_metadata={
                "schema_version": 1,
                "model": manifest.get("model") if isinstance(manifest, dict) else None,
                "prompt": info.get("prompt"),
            },
        )
        result.append(record.__dict__ | {"logical_path": relative, "kind": kind})
    return result


def publish_public_oss_references(job: dict[str, Any], job_dir: Path) -> dict[str, Any] | None:
    """Freeze public OSS URLs into playable scene files after all local assets exist."""
    if settings.oss_access_mode != "public" or not asset_library.enabled_for(job):
        return None
    records = sync_generated_job_assets(job, job_dir)
    by_path = {str(item["logical_path"]): item for item in records}
    manifest_path = job_dir / "state" / "oss_game_manifest.json"
    previous: dict[str, Any] = {}
    if manifest_path.exists():
        import json
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        previous = loaded.get("assets", {}) if isinstance(loaded, dict) else {}
    previous_url_to_path = {
        str(item.get("url")): path for path, item in previous.items()
        if isinstance(item, dict) and item.get("url")
    }

    def resolve(value: str, category: str) -> str:
        if value in {"", "none"}:
            return value
        if value in previous_url_to_path:
            logical = previous_url_to_path[value]
        elif value.startswith(("http://", "https://")):
            return value
        else:
            normalized = value.replace("\\", "/")
            normalized = normalized.removeprefix("./game/").lstrip("./")
            logical = normalized if "/" in normalized else f"{category}/{normalized}"
        record = by_path.get(logical)
        return str(record["url"]) if record else value

    command_categories = {
        "changebg": "background", "changefigure": "figure", "miniavatar": "figure",
        "bgm": "bgm", "playeffect": "vocal",
    }
    command_pattern = re.compile(
        r"^(?P<prefix>\s*(?P<command>changeBg|changeFigure|miniAvatar|bgm|playEffect)\s*:\s*)(?P<value>[^\s;]+)",
        flags=re.IGNORECASE,
    )
    vocal_pattern = re.compile(r"(?P<prefix>\s-vocal(?:=|\s))(?P<value>[^\s;]+)", flags=re.IGNORECASE)
    scene_dir = job_dir / "public" / "game" / "scene"
    rewritten: list[str] = []
    if scene_dir.exists():
        for scene_path in sorted(scene_dir.glob("*.txt")):
            original = scene_path.read_text(encoding="utf-8")
            lines: list[str] = []
            for line in original.splitlines():
                match = command_pattern.match(line)
                if match:
                    command = match.group("command")
                    category = command_categories.get(command.lower(), "")
                    replacement = resolve(match.group("value"), category)
                    line = f"{match.group('prefix')}{replacement}{line[match.end():]}"
                line = vocal_pattern.sub(
                    lambda match: f"{match.group('prefix')}{resolve(match.group('value'), 'vocal')}", line
                )
                lines.append(line)
            updated = "\n".join(lines).rstrip() + "\n"
            if updated != original:
                scene_path.write_text(updated, encoding="utf-8")
                rewritten.append(scene_path.name)
    manifest = {
        "version": 1,
        "access_mode": "public",
        "assets": {
            path: {
                "asset_id": item["asset_id"], "asset_file_id": item["file_id"],
                "revision": item["revision"], "object_key": item["object_key"], "url": item["url"],
            }
            for path, item in sorted(by_path.items())
        },
        "rewritten_scenes": rewritten,
    }
    return manifest
