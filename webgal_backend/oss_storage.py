"""Aliyun OSS operations for immutable game asset files."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from .config import settings


class OSSUploadError(RuntimeError):
    pass


@dataclass(frozen=True)
class StoredObject:
    object_key: str
    url: str
    etag: str | None


def _bucket():
    if not settings.oss_bucket or not settings.oss_access_key_id or not settings.oss_access_key_secret:
        raise OSSUploadError("OSS is not configured; set WEBGAL_OSS_BUCKET, OSS_ACCESS_KEY_ID and OSS_ACCESS_KEY_SECRET")
    try:
        import oss2
    except ImportError as exc:
        raise OSSUploadError("OSS client dependency is missing; install oss2") from exc
    auth = oss2.Auth(settings.oss_access_key_id, settings.oss_access_key_secret)
    return oss2.Bucket(auth, settings.oss_endpoint, settings.oss_bucket)


def _public_url(object_key: str) -> str:
    endpoint = urlsplit(settings.oss_endpoint)
    host = endpoint.netloc or endpoint.path
    scheme = endpoint.scheme or "https"
    return f"{scheme}://{settings.oss_bucket}.{host}/{object_key}"


def asset_object_key(
    *, user_id: str, source_type: str, asset_id: str, revision: int, file_id: str, extension: str
) -> str:
    source = source_type.lower()
    if source not in {"generated", "uploaded", "imported"}:
        raise ValueError("unsupported asset source type")
    safe_ext = extension.lower().lstrip(".")
    if not safe_ext.isalnum():
        raise ValueError("invalid asset file extension")
    parts = [settings.oss_prefix, "users", user_id, "assets", source, asset_id, f"r{revision}", f"{file_id}.{safe_ext}"]
    if any(not part or part in {".", ".."} or "/" in part or "\\" in part for part in parts[1:]):
        raise ValueError("invalid asset object key component")
    return str(PurePosixPath(*parts))


def upload_asset_file(*, object_key: str, content: bytes, content_type: str) -> StoredObject:
    bucket = _bucket()
    try:
        result = bucket.put_object(object_key, content, headers={"Content-Type": content_type})
        metadata = bucket.head_object(object_key)
    except Exception as exc:
        raise OSSUploadError("upload to OSS failed") from exc
    remote_size = int(getattr(metadata, "content_length", -1))
    if remote_size != len(content):
        raise OSSUploadError(f"OSS object size mismatch: expected {len(content)}, got {remote_size}")
    etag = str(getattr(result, "etag", "") or getattr(metadata, "etag", "") or "").strip('"') or None
    return StoredObject(object_key=object_key, url=_public_url(object_key), etag=etag)


def sign_asset_url(object_key: str, expires_seconds: int = 900) -> str:
    try:
        return _bucket().sign_url("GET", object_key, max(60, min(expires_seconds, 3600)))
    except Exception as exc:
        if isinstance(exc, OSSUploadError):
            raise
        raise OSSUploadError("unable to create OSS signed URL") from exc


def asset_access_url(object_key: str) -> str:
    mode = settings.oss_access_mode
    if mode == "public":
        return _public_url(object_key)
    if mode == "private":
        return sign_asset_url(object_key, settings.oss_signed_url_ttl)
    raise OSSUploadError("WEBGAL_OSS_ACCESS_MODE must be public or private")


def upload_public_asset(job_id: str, category: str, filename: str, content: bytes, content_type: str | None = None) -> tuple[str, str]:
    """Return the object key and its public URL; credentials never leave the server."""
    if not settings.oss_bucket or not settings.oss_access_key_id or not settings.oss_access_key_secret:
        raise OSSUploadError("OSS is not configured; set OSS_ACCESS_KEY_ID and OSS_ACCESS_KEY_SECRET on the backend")
    object_key = f"{settings.oss_prefix}/{job_id}/{category}/{filename}"
    try:
        stored = upload_asset_file(object_key=object_key, content=content, content_type=content_type or "application/octet-stream")
    except OSSUploadError:
        raise
    return stored.object_key, stored.url
