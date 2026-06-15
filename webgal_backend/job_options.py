from __future__ import annotations

from typing import Any


REQUIRED_GENERATION_OPTIONS = [
    "classroom_topic",
    "grade",
    "difficulty",
    "teacher_goal",
    "student_goal",
    "duration",
    "narrative_mode",
    "character_count",
    "interactive_task_count",
    "voice_enabled",
    "generate_assets",
]


def validate_generation_options(options: dict[str, Any]) -> None:
    missing = [key for key in REQUIRED_GENERATION_OPTIONS if key not in options]
    empty = [
        key
        for key in ["classroom_topic", "grade", "difficulty", "teacher_goal", "student_goal", "duration", "narrative_mode"]
        if key in options and not str(options.get(key, "")).strip()
    ]
    errors = []
    if missing:
        errors.append("missing required options: " + ", ".join(missing))
    if empty:
        errors.append("empty required options: " + ", ".join(empty))

    for key, minimum, maximum in [
        ("character_count", 1, 8),
        ("interactive_task_count", 1, 12),
    ]:
        if key in options:
            try:
                value = int(options[key])
            except (TypeError, ValueError):
                errors.append(f"{key} must be an integer")
                continue
            if value < minimum or value > maximum:
                errors.append(f"{key} must be between {minimum} and {maximum}")

    for key in ["voice_enabled", "generate_assets"]:
        if key in options and not isinstance(options[key], bool):
            errors.append(f"{key} must be a boolean")

    if bool(options.get("voice_enabled")) and not str(options.get("voice_preset", "")).strip():
        errors.append("voice_preset is required when voice_enabled is true")

    if errors:
        raise ValueError("; ".join(errors))
