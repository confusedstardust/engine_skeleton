from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError, field_validator, model_validator


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


class GenerationOptions(BaseModel):
    model_config = ConfigDict(extra="allow")

    classroom_topic: str
    grade: str
    difficulty: str
    teacher_goal: str
    student_goal: str
    duration: str
    narrative_mode: str
    character_count: int = Field(ge=1, le=8)
    interactive_task_count: int = Field(ge=1, le=12)
    voice_enabled: StrictBool
    generate_assets: StrictBool
    generate_tts: StrictBool | None = None
    voice_preset: str | None = None
    tts_scope: Literal["key_lines", "all"] = "key_lines"
    tts_max_lines_per_scene: int = Field(default=3, ge=1, le=20)
    tts_max_total_lines: int = Field(default=60, ge=1, le=500)
    allow_missing_assets: StrictBool = True
    output_packages: list[str] = Field(default_factory=list)

    @field_validator(
        "classroom_topic",
        "grade",
        "difficulty",
        "teacher_goal",
        "student_goal",
        "duration",
        "narrative_mode",
        mode="before",
    )
    @classmethod
    def _required_text(cls, value: Any) -> str:
        text = "" if value is None else str(value).strip()
        if not text:
            raise ValueError("must not be empty")
        return text

    @field_validator("duration")
    @classmethod
    def _duration_contains_minutes(cls, value: str) -> str:
        if not any(char.isdigit() for char in value):
            raise ValueError("must contain minutes, e.g. '20分钟'")
        return value

    @field_validator("voice_preset", mode="before")
    @classmethod
    def _normalize_optional_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @model_validator(mode="after")
    def _voice_preset_required_when_voice_enabled(self) -> "GenerationOptions":
        if self.voice_enabled and not self.voice_preset:
            raise ValueError("voice_preset is required when voice_enabled is true")
        return self


def parse_generation_options(options: dict[str, Any] | GenerationOptions) -> GenerationOptions:
    if isinstance(options, GenerationOptions):
        return options
    try:
        return GenerationOptions.model_validate(options)
    except ValidationError as exc:
        raise ValueError(_format_generation_option_errors(exc)) from exc


def normalize_generation_options(options: dict[str, Any] | GenerationOptions) -> dict[str, Any]:
    return parse_generation_options(options).model_dump(exclude_none=True)


def validate_generation_options(options: dict[str, Any] | GenerationOptions) -> GenerationOptions:
    return parse_generation_options(options)


def _format_generation_option_errors(exc: ValidationError) -> str:
    errors = exc.errors()
    missing = [str(error["loc"][0]) for error in errors if error.get("type") == "missing" and error.get("loc")]
    empty = [
        str(error["loc"][0])
        for error in errors
        if error.get("loc")
        and error["loc"][0]
        in {"classroom_topic", "grade", "difficulty", "teacher_goal", "student_goal", "duration", "narrative_mode"}
        and error.get("type", "").startswith("value_error")
    ]
    messages: list[str] = []
    if missing:
        messages.append("missing required options: " + ", ".join(missing))
    if empty:
        messages.append("empty required options: " + ", ".join(empty))

    for error in errors:
        if not error.get("loc"):
            message = str(error.get("msg", "invalid options"))
            if "voice_preset is required" in message:
                messages.append("voice_preset is required when voice_enabled is true")
            else:
                messages.append(message)
            continue
        key = str(error["loc"][0])
        error_type = str(error.get("type", ""))
        if key in missing or key in empty:
            continue
        if error_type.startswith("int_parsing"):
            messages.append(f"{key} must be an integer")
        elif key == "character_count":
            messages.append("character_count must be between 1 and 8")
        elif key == "interactive_task_count":
            messages.append("interactive_task_count must be between 1 and 12")
        elif key in {"voice_enabled", "generate_assets"}:
            messages.append(f"{key} must be a boolean")
        else:
            messages.append(f"{key}: {error.get('msg', 'invalid value')}")

    return "; ".join(dict.fromkeys(messages))
