from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .generation_limits import generation_limits
from .storage import read_json, write_json
from .tts import TTSSynthesisError, TTSOptions, synthesize_text_to_file


COMMAND_PREFIXES = (
    ":",
    "intro:",
    "choose:",
    "change",
    "miniAvatar:",
    "setVar:",
    "unlock",
    "pixi",
    "bgm:",
    "playEffect:",
    "setTransition:",
    "end",
)


def build_tts_manifest(job_dir: Path, character_voices: dict[str, list[str]] | None = None) -> dict[str, Any]:
    narrative_plan = read_json(job_dir / "state" / "narrative_plan.json")
    script_path = job_dir / "state" / "game_design_webgal.txt"
    script_text = script_path.read_text(encoding="utf-8")
    characters = _character_lookup(narrative_plan)
    character_voices = _sanitize_character_voices(
        narrative_plan,
        character_voices or _character_voice_map(narrative_plan),
    )

    items: list[dict[str, Any]] = []
    for scene_name, body in _scene_sections(script_text):
        scene_stem = _safe_filename(scene_name.removesuffix(".txt"))
        for line_no, line in enumerate(body.splitlines(), start=1):
            dialogue = _parse_dialogue_line(line)
            if not dialogue:
                continue
            speaker, text = dialogue
            character = characters.get(speaker)
            if not character:
                continue
            speaker_id = _safe_filename(str(character.get("id") or speaker))
            voice, tone = character_voices.get(speaker, [_default_voice(), ""])
            filename = f"{scene_stem}_{line_no:03d}_{speaker_id}.wav"
            items.append(
                {
                    "scene": scene_name,
                    "line_no": line_no,
                    "speaker": speaker,
                    "speaker_id": speaker_id,
                    "gender": character.get("gender", ""),
                    "voice": voice,
                    "tone": tone,
                    "text": text,
                    "filename": filename,
                    "status": "pending",
                    "error": None,
                }
            )

    return {
        "vocal_dir": "public/game/vocal",
        "character_voices": character_voices,
        "items": items,
    }


def generate_tts_audio(job_dir: Path, manifest: dict[str, Any], enabled: bool) -> dict[str, Any]:
    limits = generation_limits().get("tts", {})
    vocal_dir = job_dir / "public" / "game" / "vocal"
    vocal_dir.mkdir(parents=True, exist_ok=True)

    items = manifest.get("items", [])
    if not enabled:
        for item in items:
            item["status"] = "skipped_disabled"
        return manifest

    skip_existing = bool(limits.get("skip_existing", True))
    max_workers = max(1, int(limits.get("max_workers", 4)))
    volume = int(limits.get("volume", 50))
    speech_rate = _rate_value(limits.get("speech_rate", limits.get("speed", 1.0)))
    pitch_rate = _rate_value(limits.get("pitch_rate", limits.get("pitch", 1.0)))
    model = str(limits.get("model", "qwen3-tts-instruct-flash-realtime"))
    url = str(limits.get("url", "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"))
    optimize_instructions = bool(limits.get("optimize_instructions", True))

    def synthesize(item: dict[str, Any]) -> dict[str, Any]:
        output = vocal_dir / item["filename"]
        if skip_existing and output.exists():
            item["status"] = "skipped_existing"
            return item
        options = TTSOptions(
            voice=str(item.get("voice") or _default_voice()),
            model=model,
            url=url,
            volume=volume,
            speech_rate=speech_rate,
            pitch_rate=pitch_rate,
            instructions=_tts_instructions(item),
            optimize_instructions=optimize_instructions,
        )
        for attempt in range(4):
            try:
                synthesize_text_to_file(str(item["text"]), output, options=options)
                item["status"] = "completed"
                item["error"] = None
                return item
            except (TTSSynthesisError, RuntimeError) as exc:
                error = str(exc)
                if attempt < 3 and _is_rate_limit_error(error):
                    time.sleep(5 * (attempt + 1))
                    continue
                item["status"] = "failed"
                item["error"] = error
        return item

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(synthesize, item) for item in items]
        for future in as_completed(futures):
            future.result()

    return manifest


def write_tts_manifest(job_dir: Path, manifest: dict[str, Any]) -> None:
    write_json(job_dir / "state" / "tts_manifest.json", manifest)


def _is_rate_limit_error(error: str) -> bool:
    lowered = error.lower()
    return "rate limit" in lowered or "1007" in lowered


def _rate_value(value: Any) -> float:
    parsed = float(value)
    if parsed > 2.0:
        return max(0.5, min(2.0, parsed / 50.0))
    return max(0.5, min(2.0, parsed))


def _tts_instructions(item: dict[str, Any]) -> str:
    tone = str(item.get("tone") or "").strip()
    if not tone:
        return ""
    return f"请使用如下声线与听感进行朗读：{tone}。保持吐字清晰，情绪自然，不要夸张表演。"


def _scene_sections(script_text: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"^\s*\[([A-Za-z0-9_-]+\.txt)\]\s*$", script_text, flags=re.MULTILINE))
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(script_text)
        sections.append((match.group(1), script_text[body_start:body_end].strip()))
    return sections


def _character_lookup(narrative_plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for character in narrative_plan.get("characters", []):
        name = str(character.get("name", "")).strip()
        if name:
            lookup[name] = character
    return lookup


def _character_voice_map(narrative_plan: dict[str, Any]) -> dict[str, list[str]]:
    voices = generation_limits().get("tts", {}).get("voices", {})
    male_voices = _voice_pool(voices.get("male"), [_default_voice()])
    female_voices = _voice_pool(voices.get("female"), [_default_voice()])
    fallback = str(voices.get("default") or _default_voice())
    gender_counts = {"male": 0, "female": 0}
    mapping: dict[str, list[str]] = {}

    for character in narrative_plan.get("characters", []):
        name = str(character.get("name", "")).strip()
        if not name:
            continue
        gender = _normalize_gender(character.get("gender"))
        if gender == "male":
            voice = male_voices[gender_counts["male"] % len(male_voices)]
            gender_counts["male"] += 1
        elif gender == "female":
            voice = female_voices[gender_counts["female"] % len(female_voices)]
            gender_counts["female"] += 1
        else:
            voice = fallback
        mapping[name] = [voice, ""]
    return mapping


def _sanitize_character_voices(narrative_plan: dict[str, Any], character_voices: dict[str, list[str]]) -> dict[str, list[str]]:
    valid_voices = _valid_voice_names()
    sanitized: dict[str, list[str]] = {}
    for character in narrative_plan.get("characters", []):
        name = str(character.get("name", "")).strip()
        if not name:
            continue
        assignment = character_voices.get(name, ["", ""])
        if not isinstance(assignment, list) or len(assignment) != 2:
            assignment = ["", ""]
        voice = str(assignment[0]).strip()
        tone = str(assignment[1]).strip()
        if voice not in valid_voices:
            voice = _fallback_voice_for_gender(character.get("gender"))
        sanitized[name] = [voice, tone]
    return sanitized


def _normalize_gender(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "unknown"
    if any(marker in text for marker in ("女性", "女人", "女子", "女", "female", "woman", "girl")):
        return "female"
    if any(marker in text for marker in ("男性", "男人", "男子", "男", "male", "man", "boy")):
        return "male"
    return "unknown"


def _voice_pool(value: Any, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        voices = [str(item).strip() for item in value if str(item).strip()]
        if voices:
            return voices
    if isinstance(value, dict):
        voices = [str(item).strip() for item in value.keys() if str(item).strip()]
        if voices:
            return voices
    return fallback


def _default_voice() -> str:
    voices = generation_limits().get("tts", {}).get("voices", {})
    default = str(voices.get("default") or generation_limits().get("tts", {}).get("voice") or "").strip()
    if default and default in _valid_voice_names():
        return default
    for voice in _voice_names_in_config_order():
        return voice
    return "Cherry"


def _fallback_voice_for_gender(gender_value: Any) -> str:
    voices = generation_limits().get("tts", {}).get("voices", {})
    gender = _normalize_gender(gender_value)
    if gender == "male":
        return _voice_pool(voices.get("male"), [_default_voice()])[0]
    if gender == "female":
        return _voice_pool(voices.get("female"), [_default_voice()])[0]
    return _default_voice()


def _valid_voice_names() -> set[str]:
    return set(_voice_names_in_config_order())


def _voice_names_in_config_order() -> list[str]:
    voices = generation_limits().get("tts", {}).get("voices", {})
    names: list[str] = []
    for key in ("male", "female"):
        value = voices.get(key)
        if isinstance(value, dict):
            names.extend(str(item).strip() for item in value.keys() if str(item).strip())
        elif isinstance(value, list):
            names.extend(str(item).strip() for item in value if str(item).strip())
    return list(dict.fromkeys(names))


def _parse_dialogue_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith((";", "//")) or stripped.startswith(COMMAND_PREFIXES):
        return None
    match = re.match(r"^(?P<speaker>[^:\uFF1A;\s][^:\uFF1A;]*?)\s*[\uFF1A:]\s*(?P<body>.+?)\s*;?\s*$", stripped)
    if not match:
        return None
    speaker = match.group("speaker").strip()
    if speaker in {"if", "label", "jumpLabel", "callScene"}:
        return None
    text = _strip_webgal_args(match.group("body").strip())
    text = text.strip().strip('"').strip("'").strip()
    if not text:
        return None
    return speaker, text


def _strip_webgal_args(text: str) -> str:
    text = text.rstrip(";").strip()
    arg_match = re.search(r"\s-[A-Za-z][A-Za-z0-9_-]*(?:=|\s|$)", text)
    if arg_match:
        return text[: arg_match.start()].strip()
    return text


def _safe_filename(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_").lower()
    return safe or "line"
