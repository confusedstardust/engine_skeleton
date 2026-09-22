from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .storage import read_json


class TeacherEcosystemError(RuntimeError):
    pass


def _configuration() -> tuple[str, str]:
    api_url = os.getenv("TEACHER_ECOSYSTEM_API_URL", "").strip().rstrip("/")
    token = os.getenv("TEACHER_ECOSYSTEM_SERVICE_TOKEN", "").strip()
    if not api_url:
        raise TeacherEcosystemError("TEACHER_ECOSYSTEM_API_URL is not configured")
    if not token:
        raise TeacherEcosystemError("TEACHER_ECOSYSTEM_SERVICE_TOKEN is not configured")
    return api_url, token


def _request(method: str, *, query: dict[str, str] | None = None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    api_url, token = _configuration()
    url = api_url
    if query:
        url = f"{url}?{urlencode(query)}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = Request(
        url,
        data=data,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            **({"Content-Type": "application/json"} if data is not None else {}),
        },
        method=method,
    )
    try:
        with urlopen(request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            message = json.loads(body).get("error") or body
        except json.JSONDecodeError:
            message = body
        raise TeacherEcosystemError(f"教师生态服务返回 HTTP {exc.code}: {message}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise TeacherEcosystemError(f"无法连接教师生态服务: {exc}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TeacherEcosystemError("教师生态服务返回了无效响应") from exc
    if not isinstance(result, dict):
        raise TeacherEcosystemError("教师生态服务返回了无效响应")
    return result


def publication_status(job_id: str) -> dict[str, Any]:
    return _request("GET", query={"jobId": job_id})


def publish_work(payload: dict[str, Any]) -> dict[str, Any]:
    return _request("POST", payload=payload)


def unpublish_work(owner_user_id: str, job_id: str) -> dict[str, Any]:
    return _request("DELETE", payload={"ownerUserId": owner_user_id, "jobId": job_id})


def build_publication_payload(
    *,
    job: dict[str, Any],
    job_dir: Path,
    user: dict[str, Any],
    frontend_url: str,
    title_override: str | None = None,
) -> dict[str, Any]:
    options = job.get("options") if isinstance(job.get("options"), dict) else {}
    narrative = _read_optional_json(job_dir / "state" / "narrative_plan.json")
    title = (
        (title_override or "").strip()
        or str(options.get("classroom_topic") or "").strip()
        or str(narrative.get("title") or "").strip()
        or "未命名叙事课堂"
    )[:160]
    summary = str(narrative.get("theme") or narrative.get("story_arc") or "").strip()[:2000] or None
    grade = str(options.get("grade") or "").strip()[:80] or None
    narrative_mode = str(options.get("narrative_mode") or "").strip()
    tags = [value for value in [narrative_mode, str(narrative.get("emotion_tone") or "").strip()] if value]
    root = frontend_url.rstrip("/")
    job_id = str(job["id"])
    has_quiz = (job_dir / "state" / "quiz_plan.json").exists()
    return {
        "ownerUserId": str(user["id"]),
        "authorName": user.get("nickname") or ((user.get("email") or "").split("@")[0] or None),
        "jobId": job_id,
        "title": title,
        "summary": summary,
        "coverUrl": _cover_url(root, job_id, job_dir),
        "playUrl": f"{root}/play/{job_id}/",
        "quizUrl": f"{root}/practice/{job_id}/" if has_quiz else None,
        "subject": _subject_from_grade(grade),
        "grade": grade,
        "tags": tags[:8],
    }


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = read_json(path)
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _cover_url(root: str, job_id: str, job_dir: Path) -> str | None:
    background_dir = job_dir / "public" / "game" / "background"
    if not background_dir.exists():
        return None
    candidates = sorted(
        path.name
        for path in background_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    )
    if not candidates:
        return None
    preferred = next((name for name in candidates if name.lower().startswith(("title", "bg_start", "bg_"))), candidates[0])
    return f"{root}/play/{job_id}/game/background/{quote(preferred)}"


def _subject_from_grade(grade: str | None) -> str | None:
    if not grade:
        return None
    subjects = ["语文", "数学", "英语", "历史", "地理", "物理", "化学", "生物", "道德与法治", "信息科技", "科学"]
    return next((subject for subject in subjects if subject in grade), None)
