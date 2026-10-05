from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Mapping


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except ValueError:
        return default


@dataclass(frozen=True)
class Pricing:
    text_input_per_million: int = 200
    text_output_per_million: int = 800
    image_each: int = 10
    tts_per_thousand_characters: int = 5
    text_hold: int = 20
    image_hold: int = 50
    tts_hold: int = 30

    @classmethod
    def from_env(cls) -> "Pricing":
        return cls(
            text_input_per_million=_env_int("CREDIT_TEXT_INPUT_PER_MILLION", 200),
            text_output_per_million=_env_int("CREDIT_TEXT_OUTPUT_PER_MILLION", 800),
            image_each=_env_int("CREDIT_IMAGE_EACH", 10),
            tts_per_thousand_characters=_env_int("CREDIT_TTS_PER_THOUSAND_CHARACTERS", 5),
            text_hold=_env_int("CREDIT_TEXT_HOLD", 20),
            image_hold=_env_int("CREDIT_IMAGE_HOLD", 50),
            tts_hold=_env_int("CREDIT_TTS_HOLD", 30),
        )


@dataclass(frozen=True)
class UsageSnapshot:
    traces: tuple[str, ...]
    images: tuple[tuple[str, int], ...]
    vocals: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class UsageTotals:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    images: int = 0
    tts_characters: int = 0


def _files(root: Path, pattern: str) -> tuple[tuple[str, int], ...]:
    if not root.exists():
        return ()
    return tuple(sorted((str(path.resolve()), path.stat().st_mtime_ns) for path in root.glob(pattern) if path.is_file()))


def _billable_image_files(job_dir: Path) -> tuple[tuple[str, int], ...]:
    manifest_path = job_dir / "assets_manifest.json"
    if not manifest_path.exists():
        return ()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        images = manifest.get("images", [])
    except (OSError, json.JSONDecodeError, AttributeError):
        return ()
    result: list[tuple[str, int]] = []
    for item in images:
        if not isinstance(item, dict):
            continue
        subdir = str(item.get("subdir") or "").strip("/\\")
        filename = str(item.get("filename") or "").strip()
        if not subdir or not filename or ".." in Path(subdir).parts:
            continue
        if not filename.lower().endswith(".webp"):
            filename += ".webp"
        for game_root in (job_dir / "public" / "game", job_dir / "draft" / "game"):
            path = game_root / subdir / filename
            if path.is_file():
                result.append((str(path.resolve()), path.stat().st_mtime_ns))
    return tuple(sorted(result))


def snapshot(job_dir: Path) -> UsageSnapshot:
    trace_dir = job_dir / "state" / "llm_traces"
    traces = tuple(sorted(str(path.resolve()) for path in trace_dir.glob("*.json"))) if trace_dir.exists() else ()
    return UsageSnapshot(
        traces=traces,
        images=_billable_image_files(job_dir),
        vocals=_files(job_dir / "public" / "game", "**/*.wav") + _files(job_dir / "draft" / "game", "**/*.wav"),
    )


def estimate_hold(options: Mapping[str, Any], pricing: Pricing | None = None) -> tuple[int, dict[str, Any]]:
    pricing = pricing or Pricing.from_env()
    parts = {"text": pricing.text_hold, "images": 0, "tts": 0}
    if bool(options.get("generate_assets", False)):
        parts["images"] = pricing.image_hold
    if bool(options.get("generate_tts", options.get("voice_enabled", False))):
        parts["tts"] = pricing.tts_hold
    units = max(1, sum(parts.values()))
    return units, {"schema_version": 2, "plan": "metered_generation_v1", "hold_parts": parts, "pricing": asdict(pricing)}


def _usage_number(usage: Mapping[str, Any], *names: str) -> int:
    for name in names:
        value = usage.get(name)
        if isinstance(value, (int, float)) and value >= 0:
            return int(value)
    return 0


def measure(job_dir: Path, before: UsageSnapshot) -> UsageTotals:
    known_traces = set(before.traces)
    input_tokens = output_tokens = cached_tokens = 0
    trace_dir = job_dir / "state" / "llm_traces"
    for path in trace_dir.glob("*.json") if trace_dir.exists() else ():
        if str(path.resolve()) in known_traces:
            continue
        try:
            usage = json.loads(path.read_text(encoding="utf-8")).get("usage") or {}
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(usage, dict):
            continue
        input_tokens += _usage_number(usage, "input_tokens", "prompt_tokens")
        output_tokens += _usage_number(usage, "output_tokens", "completion_tokens")
        details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}
        if isinstance(details, dict):
            cached_tokens += _usage_number(details, "cached_tokens", "cached_input_tokens")

    before_images = dict(before.images)
    after_images = dict(_billable_image_files(job_dir))
    changed_images = {path for path, modified in after_images.items() if before_images.get(path) != modified}

    before_vocals = dict(before.vocals)
    after_vocals = dict(_files(job_dir / "public" / "game", "**/*.wav") + _files(job_dir / "draft" / "game", "**/*.wav"))
    changed_vocals = {path for path, modified in after_vocals.items() if before_vocals.get(path) != modified}
    tts_characters = 0
    for manifest_name, items_key, default_dir in (
        ("tts_manifest.json", "items", "public/game/vocal"),
        ("tts_voice_review.json", "characters", "public/game/vocal_preview"),
    ):
        manifest_path = job_dir / "state" / manifest_name
        if not changed_vocals or not manifest_path.exists():
            continue
        try:
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
            vocal_dir = str(document.get("vocal_dir") or default_dir).replace("\\", "/").strip("/")
            items = document.get(items_key, [])
            for item in items:
                if not isinstance(item, dict):
                    continue
                path = str((job_dir / vocal_dir / str(item.get("filename") or "")).resolve())
                if path in changed_vocals:
                    tts_characters += len(str(item.get("text") or ""))
        except (OSError, json.JSONDecodeError, AttributeError):
            pass
    return UsageTotals(input_tokens, output_tokens, cached_tokens, len(changed_images), tts_characters)


def credits_for_usage(usage: UsageTotals, pricing: Pricing | None = None) -> tuple[int, dict[str, Any]]:
    pricing = pricing or Pricing.from_env()
    billable_input = max(0, usage.input_tokens - usage.cached_input_tokens)
    text_raw = (billable_input * pricing.text_input_per_million + usage.output_tokens * pricing.text_output_per_million) / 1_000_000
    text = math.ceil(text_raw) if text_raw else 0
    images = usage.images * pricing.image_each
    tts = math.ceil(usage.tts_characters / 1000 * pricing.tts_per_thousand_characters) if usage.tts_characters else 0
    units = text + images + tts
    return units, {"schema_version": 2, "usage": asdict(usage), "charge_parts": {"text": text, "images": images, "tts": tts}, "pricing": asdict(pricing)}
