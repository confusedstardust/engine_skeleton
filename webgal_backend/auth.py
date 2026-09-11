from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from fastapi import HTTPException, Request


INVITE_HEADER_NAME = "X-WebGAL-Invite-Code"
INVITE_CODES_ENV = "WEBGAL_INVITE_CODES"
INVITE_CODES_FILE_ENV = "WEBGAL_INVITE_CODES_FILE"
AUTH_MODE_ENV = "WEBGAL_AUTH_MODE"
SSO_USERINFO_URL_ENV = "WEBGAL_SSO_USERINFO_URL"
SSO_COOKIE_NAME_ENV = "WEBGAL_SSO_COOKIE_NAME"
SSO_TIMEOUT_ENV = "WEBGAL_SSO_TIMEOUT_SECONDS"

AUTH_MODE_INVITE = "invite"
AUTH_MODE_SSO = "sso"
AUTH_MODE_HYBRID = "sso_or_invite"
AUTH_MODES = {AUTH_MODE_INVITE, AUTH_MODE_SSO, AUTH_MODE_HYBRID}


def _invite_hash(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def _invite_hash_from_entry(entry: str) -> str | None:
    value = entry.strip()
    if not value or value.startswith("#"):
        return None
    if value.startswith("sha256:"):
        digest = value.removeprefix("sha256:").strip().lower()
        return digest if re.fullmatch(r"[a-f0-9]{64}", digest) else None
    return _invite_hash(value)


def _configured_invite_hashes(workspace_root: Path) -> tuple[set[str], bool]:
    configured = False
    hashes: set[str] = set()

    raw = os.getenv(INVITE_CODES_ENV, "").strip()
    if raw:
        configured = True
        for item in re.split(r"[\s,;]+", raw):
            digest = _invite_hash_from_entry(item)
            if digest:
                hashes.add(digest)

    file_value = os.getenv(INVITE_CODES_FILE_ENV, "").strip()
    if file_value:
        configured = True
        path = Path(file_value)
        if not path.is_absolute():
            path = (workspace_root / path).resolve()
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                digest = _invite_hash_from_entry(line)
                if digest:
                    hashes.add(digest)

    return hashes, configured


def _auth_mode() -> str:
    configured = os.getenv(AUTH_MODE_ENV, "").strip().lower()
    if not configured:
        return AUTH_MODE_SSO if os.getenv(SSO_USERINFO_URL_ENV, "").strip() else AUTH_MODE_INVITE
    if configured not in AUTH_MODES:
        raise HTTPException(status_code=503, detail=f"unsupported {AUTH_MODE_ENV}: {configured}")
    return configured


def _sso_cookie_name() -> str:
    name = os.getenv(SSO_COOKIE_NAME_ENV, "nos_session").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise HTTPException(status_code=503, detail=f"invalid {SSO_COOKIE_NAME_ENV}")
    return name


def _sso_timeout() -> float:
    try:
        value = float(os.getenv(SSO_TIMEOUT_ENV, "5"))
    except ValueError:
        value = 5.0
    return min(max(value, 0.25), 30.0)


def _sso_user_from_request(request: Request) -> dict[str, Any]:
    userinfo_url = os.getenv(SSO_USERINFO_URL_ENV, "").strip()
    parsed = urlsplit(userinfo_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=503, detail=f"{SSO_USERINFO_URL_ENV} is not configured")

    cookie_name = _sso_cookie_name()
    token = request.cookies.get(cookie_name, "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="SSO login is required")
    if not re.fullmatch(r"[A-Za-z0-9._~-]+", token):
        raise HTTPException(status_code=401, detail="SSO session is invalid or expired")

    upstream = UrlRequest(
        userinfo_url,
        headers={
            "Accept": "application/json",
            "Cookie": f"{cookie_name}={token}",
            "User-Agent": "WebGAL-Forge-SSO/1.0",
        },
        method="GET",
    )
    try:
        with urlopen(upstream, timeout=_sso_timeout()) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise HTTPException(status_code=401, detail="SSO session is invalid or expired") from exc
        raise HTTPException(status_code=503, detail="SSO service is unavailable") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise HTTPException(status_code=503, detail="SSO service is unavailable") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail="SSO service returned an invalid response") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="SSO service returned an invalid response")
    user_id = str(payload.get("id") or "").strip()
    if not user_id:
        raise HTTPException(status_code=502, detail="SSO response is missing user id")

    providers = payload.get("providers")
    return {
        "id": user_id,
        "email": payload.get("email") if isinstance(payload.get("email"), str) else None,
        "nickname": payload.get("nickname") if isinstance(payload.get("nickname"), str) else None,
        "avatar_url": payload.get("avatarUrl") if isinstance(payload.get("avatarUrl"), str) else None,
        "providers": [item for item in providers if isinstance(item, str)] if isinstance(providers, list) else [],
        "auth_type": "sso",
    }


def _invite_principal(request: Request, workspace_root: Path) -> dict[str, Any]:
    code = unquote(request.headers.get(INVITE_HEADER_NAME) or "").strip()
    if not code:
        raise HTTPException(status_code=401, detail="invite code is required")
    invite_hash = _invite_hash(code)
    allowed, configured = _configured_invite_hashes(workspace_root)
    if configured and invite_hash not in allowed:
        raise HTTPException(status_code=403, detail="invalid invite code")
    return {
        "identity": {"type": "invite", "invite_hash": invite_hash},
        "user": {
            "id": f"invite:{invite_hash[:16]}",
            "email": None,
            "nickname": None,
            "avatar_url": None,
            "providers": [],
            "auth_type": "invite",
        },
    }


def principal_from_request(request: Request, workspace_root: Path) -> dict[str, Any]:
    mode = _auth_mode()
    if mode in {AUTH_MODE_SSO, AUTH_MODE_HYBRID}:
        cookie_name = _sso_cookie_name()
        if request.cookies.get(cookie_name):
            user = _sso_user_from_request(request)
            return {
                "identity": {"type": "sso", "user_id": user["id"]},
                "user": user,
            }
        if mode == AUTH_MODE_SSO:
            raise HTTPException(status_code=401, detail="SSO login is required")
    return _invite_principal(request, workspace_root)


def identity_from_request(request: Request, workspace_root: Path) -> dict[str, str]:
    return principal_from_request(request, workspace_root)["identity"]


def user_from_request(request: Request, workspace_root: Path) -> dict[str, Any]:
    return principal_from_request(request, workspace_root)["user"]


def job_belongs_to_identity(job: dict[str, Any], identity: dict[str, str]) -> bool:
    stored = job.get("identity")
    if not isinstance(stored, dict) or stored.get("type") != identity.get("type"):
        return False
    if identity.get("type") == "sso":
        return stored.get("user_id") == identity.get("user_id")
    return stored.get("invite_hash") == identity.get("invite_hash")
