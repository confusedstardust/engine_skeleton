from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import settings


REQUIRED_PATHS = [
    ("characters", "min"),
    ("characters", "max"),
    ("variables", "max_total"),
    ("variables", "attitude_max"),
    ("variables", "flag_max"),
    ("variables", "attitude_min_value"),
    ("variables", "attitude_max_value"),
    ("scenes", "min"),
    ("scenes", "max"),
    ("scenes", "min_lines"),
    ("scenes", "max_lines"),
    ("branches", "min"),
    ("branches", "max"),
    ("branches", "max_depth"),
    ("branches", "choice_options_min"),
    ("branches", "choice_options_max"),
    ("branches", "preferred_choice_points"),
    ("endings", "categories"),
    ("assets", "figure_subdir"),
    ("assets", "figure_size"),
    ("assets", "background_subdir"),
    ("assets", "background_size"),
]

def limits_path() -> Path:
    configured = os.getenv("WEBGAL_GENERATION_LIMITS")
    if configured:
        path = Path(configured)
        return path if path.is_absolute() else (settings.workspace_root / path).resolve()
    return settings.workspace_root / "webgal_backend" / "generation_limits.json"


@lru_cache(maxsize=1)
def generation_limits() -> dict[str, Any]:
    path = limits_path()
    if not path.exists():
        raise FileNotFoundError(f"generation limits config not found: {path}")

    limits = json.loads(path.read_text(encoding="utf-8"))
    _validate_limits(limits, path)
    _derive_limits(limits)
    return limits


def prompt_limits_text() -> str:
    limits = generation_limits()
    endings = ", ".join(limits["endings"]["categories"])
    return "\n".join(
        [
            f"- {limits['characters']['min']} to {limits['characters']['max']} characters.",
            "- Exactly one protagonist.",
            f"- No more than {limits['variables']['max_total']} global variables total.",
            f"- Attitude variables: at most {limits['variables']['attitude_max']}, range {limits['variables']['attitude_min_value']}-{limits['variables']['attitude_max_value']}.",
            f"- Flag variables: at most {limits['variables']['flag_max']}, using 0/1 values.",
            f"- {limits['scenes']['min']} to {limits['scenes']['max']} scenes including ending scenes.",
            f"- {limits['branches']['min']} to {limits['branches']['max']} meaningful choice points; {limits['branches']['preferred_choice_points']} is preferred for richer stories.",
            f"- Choice points must have {limits['branches']['choice_options_min']} to {limits['branches']['choice_options_max']} options.",
            f"- Exactly {limits['endings']['count']} endings: {endings}.",
            f"- Branch depth must not exceed {limits['branches']['max_depth']}.",
        ]
    )


def character_limits_text() -> str:
    limits = generation_limits()
    return f"- Generate {limits['characters']['min']} to {limits['characters']['max']} characters."


def _validate_limits(limits: dict[str, Any], path: Path) -> None:
    missing = [".".join(parts) for parts in REQUIRED_PATHS if _get_nested(limits, parts) is None]
    if missing:
        raise ValueError(f"{path} is missing required generation limit keys: {', '.join(missing)}")

    categories = limits["endings"]["categories"]
    if not isinstance(categories, list) or not categories:
        raise ValueError(f"{path} endings.categories must be a non-empty array")
    if "default" not in categories:
        raise ValueError(f"{path} endings.categories must include default")


def _derive_limits(limits: dict[str, Any]) -> None:
    limits["endings"]["count"] = len(limits["endings"]["categories"])
    limits["assets"]["allowed_sizes"] = list(
        dict.fromkeys([limits["assets"]["background_size"], limits["assets"]["figure_size"]])
    )


def _get_nested(data: dict[str, Any], parts: tuple[str, ...]) -> Any:
    current: Any = data
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current
