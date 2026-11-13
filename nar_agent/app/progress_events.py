"""Observable, user-facing creation milestones (not private model reasoning).

Events are derived from real Agent/tool transitions and optional explicit design
summaries. Never persist model chain-of-thought or tool arguments in this feed.
"""
from datetime import datetime, timezone

PHASES = {
    "DESIGNING": ("理解学习需求", "正在理解希望学习和操作的内容"),
    "PLANNING": ("规划学习交互", "正在选择合适的呈现与练习方式"),
    "DRAFTING": ("制作互动内容", "正在组织页面内容及互动控件"),
    "BUILDING": ("组装学习作品", "正在将创作内容转换为可操作的网页"),
    "CHECKING": ("检查作品", "正在检查网页是否可以正常显示与操作"),
    "FINALIZING": ("整理作品", "正在保存经过检查的作品"),
}


def _time():
    return datetime.now(timezone.utc)


def _stamp(now):
    return now.isoformat(timespec="milliseconds")


def _duration(started: str, now):
    return max(0, int((now - datetime.fromisoformat(started)).total_seconds() * 1000))


def enter_phase(progress: dict, phase: str, detail: str | None = None):
    """Start a real milestone and complete the preceding one exactly once."""
    if phase not in PHASES:
        raise ValueError("Unknown progress phase")
    now = _time()
    timeline = progress.setdefault("timeline", [])
    detail = detail.strip()[:160] if isinstance(detail, str) else None
    current = timeline[-1] if timeline else None
    if current and current["phase"] == phase and current["status"] == "running":
        if detail:
            current["detail"] = detail
        return
    if current and current["status"] == "running":
        current.update(status="completed", completed_at=_stamp(now),
                       duration_ms=_duration(current["started_at"], now))
    title, fallback_detail = PHASES[phase]
    timeline.append({
        "id": f"{len(timeline) + 1}",
        "phase": phase,
        "title": title,
        "detail": detail or fallback_detail,
        "status": "running",
        "started_at": _stamp(now),
        "completed_at": None,
        "duration_ms": None,
    })
    progress["phase"] = phase
    progress.setdefault("started_at", _stamp(now))
    progress["elapsed_ms"] = _duration(progress["started_at"], now)


def close_phase(progress: dict, *, failed: bool = False):
    """Close the actual last stage, including failure. Safe to call repeatedly."""
    now = _time()
    timeline = progress.get("timeline", [])
    if timeline and timeline[-1]["status"] == "running":
        current = timeline[-1]
        current.update(status="failed" if failed else "completed",
                       completed_at=_stamp(now),
                       duration_ms=_duration(current["started_at"], now))
    if progress.get("started_at"):
        progress["elapsed_ms"] = _duration(progress["started_at"], now)


def public_elapsed_ms(progress: dict) -> int:
    """Server time, rather than client clock, is authoritative."""
    if progress.get("status") == "RUNNING" and progress.get("started_at"):
        return _duration(progress["started_at"], _time())
    return progress.get("elapsed_ms", 0)
