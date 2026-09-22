"""Project-scoped Aliyun OSS upload for user-provided game assets."""
from __future__ import annotations

from .config import settings


class OSSUploadError(RuntimeError):
    pass


def upload_public_asset(job_id: str, category: str, filename: str, content: bytes, content_type: str | None = None) -> tuple[str, str]:
    """Return the object key and its public URL; credentials never leave the server."""
    if not settings.oss_bucket or not settings.oss_access_key_id or not settings.oss_access_key_secret:
        raise OSSUploadError("OSS is not configured; set OSS_ACCESS_KEY_ID and OSS_ACCESS_KEY_SECRET on the backend")
    try:
        import oss2
    except ImportError as exc:
        raise OSSUploadError("OSS client dependency is missing; install oss2") from exc
    object_key = f"{settings.oss_prefix}/{job_id}/{category}/{filename}"
    auth = oss2.Auth(settings.oss_access_key_id, settings.oss_access_key_secret)
    bucket = oss2.Bucket(auth, settings.oss_endpoint, settings.oss_bucket)
    headers = {"Content-Type": content_type} if content_type else None
    try:
        bucket.put_object(object_key, content, headers=headers)
    except Exception as exc:
        raise OSSUploadError("upload to OSS failed") from exc
    return object_key, f"https://{settings.oss_bucket}.oss-cn-hangzhou.aliyuncs.com/{object_key}"
