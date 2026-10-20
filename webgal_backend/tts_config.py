"""Validated TTS profiles and immutable, secret-free task snapshots."""
from __future__ import annotations

import copy
import json
import math
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .config import settings
from .tts import TTSConfigError

PROVIDERS = {"qwen", "doubao"}
PROFILE_FIELDS = {
    "id", "label", "enabled", "provider", "endpoint", "default_voice",
    "voices", "auth", "options",
}
OPTION_FIELDS = {
    "model", "max_workers", "volume", "speech_rate", "pitch_rate",
    "optimize_instructions", "resource_id",
}


def validate_profile(profile: Any) -> dict[str, Any]:
    if not isinstance(profile, dict):
        raise TTSConfigError("TTS profile must be an object")
    if set(profile) - PROFILE_FIELDS:
        raise TTSConfigError("Unknown TTS profile fields; store credentials only in environment variables")
    for key in ("id", "label", "provider", "endpoint", "default_voice"):
        if not isinstance(profile.get(key), str) or not profile[key].strip():
            raise TTSConfigError(f"TTS profile requires {key}")
    if profile["provider"] not in PROVIDERS:
        raise TTSConfigError(f"Unsupported TTS provider: {profile['provider']}")
    url = urlparse(profile["endpoint"])
    expected_scheme = "https" if profile["provider"] == "doubao" else "wss"
    if (
        url.scheme != expected_scheme or not url.netloc
        or url.username or url.password or url.query or url.fragment
    ):
        raise TTSConfigError("TTS endpoint must use the provider's secure protocol and contain no credentials/query")
    auth = profile.get("auth", {})
    if (
        not isinstance(auth, dict) or set(auth) != {"api_key_env"}
        or not isinstance(auth["api_key_env"], str)
        or not re.fullmatch(r"[A-Z][A-Z0-9_]*", auth["api_key_env"])
    ):
        raise TTSConfigError("TTS auth must contain only an api_key_env environment variable name")
    voices = profile.get("voices")
    if not isinstance(voices, list) or not voices:
        raise TTSConfigError("TTS profile requires a nonempty voice library")
    ids: set[str] = set()
    for voice in voices:
        if (
            not isinstance(voice, dict)
            or set(voice) != {"id", "label", "gender", "description"}
            or any(
                not isinstance(voice.get(key), str) or not voice[key].strip()
                for key in ("id", "label", "description")
            )
            or voice.get("gender") not in {"male", "female"}
        ):
            raise TTSConfigError("Each TTS voice requires id, label, gender and description")
        if voice["id"] in ids:
            raise TTSConfigError(f"Duplicate TTS voice: {voice['id']}")
        ids.add(voice["id"])
    if profile["default_voice"] not in ids:
        raise TTSConfigError("TTS default_voice is missing from its voice library")
    options = profile.get("options", {})
    if not isinstance(options, dict):
        raise TTSConfigError("TTS options must be an object")
    if set(options) - OPTION_FIELDS:
        raise TTSConfigError(f"Unsupported TTS options: {sorted(set(options) - OPTION_FIELDS)}")
    ranges = (
        ("max_workers", 1, 16, 1), ("volume", 0, 100, 50),
        ("speech_rate", 0.5, 2, 1), ("pitch_rate", 0.5, 2, 1),
    )
    for key, low, high, default in ranges:
        value = options.get(key, default)
        if (
            isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not low <= value <= high
        ):
            raise TTSConfigError(f"TTS {key} must be between {low} and {high}")
        if key in {"max_workers", "volume"} and not isinstance(value, int):
            raise TTSConfigError(f"TTS {key} must be an integer")
    if "optimize_instructions" in options and not isinstance(options["optimize_instructions"], bool):
        raise TTSConfigError("TTS optimize_instructions must be a boolean")
    if profile["provider"] == "doubao":
        if options.get("resource_id") != "seed-tts-2.0" or options.get("model"):
            raise TTSConfigError("Doubao supports preset TTS 2.0 voices with resource_id=seed-tts-2.0; cloning models are not supported")
    elif not isinstance(options.get("model"), str) or not options["model"]:
        raise TTSConfigError("Qwen TTS requires a model")
    if "enabled" in profile and not isinstance(profile["enabled"], bool):
        raise TTSConfigError("TTS enabled must be a boolean")
    return copy.deepcopy(profile)


def load_tts_profiles() -> dict[str, Any]:
    configured = Path(os.getenv("WEBGAL_TTS_PROFILES", "webgal_backend/tts_profiles.json"))
    path = configured if configured.is_absolute() else settings.workspace_root / configured
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TTSConfigError(f"Cannot read TTS profile catalog: {path}") from exc
    if (
        not isinstance(document, dict) or document.get("schema_version") != 1
        or not isinstance(document.get("profiles"), list)
    ):
        raise TTSConfigError("TTS catalog requires schema_version=1 and a profiles array")
    profiles: dict[str, dict[str, Any]] = {}
    for raw in document["profiles"]:
        profile = validate_profile(raw)
        if profile["id"] in profiles:
            raise TTSConfigError(f"Duplicate TTS profile: {profile['id']}")
        profiles[profile["id"]] = profile
    default = document.get("default_profile")
    if (
        not isinstance(default, str) or default not in profiles
        or not profiles[default].get("enabled", True)
    ):
        raise TTSConfigError("TTS default_profile must reference an enabled profile")
    return {"default_profile": default, "profiles": profiles}


def default_tts_profile(profile_id: str | None = None) -> dict[str, Any]:
    catalog = load_tts_profiles()
    profile = catalog["profiles"].get(profile_id or catalog["default_profile"])
    if not profile or not profile.get("enabled", True):
        raise TTSConfigError(f"TTS profile is unavailable: {profile_id}")
    return profile


def job_tts_profile(job_dir: Path, *, new_job: bool = False) -> dict[str, Any]:
    from .storage import write_json
    path = job_dir / "state" / "tts_profile.json"
    if path.exists():
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            if document.get("schema_version") != 1:
                raise ValueError("unsupported snapshot version")
            return validate_profile(document["profile"])
        except (OSError, ValueError, KeyError, AttributeError) as exc:
            raise TTSConfigError("Invalid task TTS profile snapshot") from exc
    # Historical tasks predate providers. Never silently switch their Qwen voices.
    legacy = not new_job and (
        (job_dir / "job.json").exists()
        or any(
            (job_dir / "state" / name).exists()
            for name in ("tts_voice_review.json", "tts_manifest.json")
        )
    )
    profile = default_tts_profile("qwen-realtime" if legacy else None)
    write_json(path, {"schema_version": 1, "profile": profile})
    return profile


def tts_settings(profile: dict[str, Any]) -> dict[str, Any]:
    """Adapt one profile into the existing pipeline's voice-assignment contract."""
    voices: dict[str, Any] = {"male": {}, "female": {}, "default": profile["default_voice"]}
    for voice in profile["voices"]:
        voices[voice["gender"]][voice["id"]] = voice["description"]
    return {**profile.get("options", {}), "voices": voices, "url": profile["endpoint"]}
