from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .scene_headers import scene_sections
from .generation_limits import generation_limits
from .storage import read_json, write_json
from .tts import TTSSynthesisError, synthesize_text_to_file, options_from_profile, cached_synthesis
from .tts_config import default_tts_profile, job_tts_profile, tts_settings


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


def build_tts_manifest(
    job_dir: Path,
    character_voices: dict[str, list[str]] | None = None,
    selection_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = job_tts_profile(job_dir)
    narrative_plan = read_json(job_dir / "state" / "narrative_plan.json")
    script_path = job_dir / "state" / "game_design_webgal.txt"
    script_text = script_path.read_text(encoding="utf-8")
    characters = _character_lookup(narrative_plan)
    character_voices = _sanitize_character_voices(
        narrative_plan,
        character_voices or _character_voice_map(narrative_plan, profile),
        profile,
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
            voice, tone = character_voices.get(speaker, [_default_voice(profile), ""])
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

    selection = _tts_selection(selection_options or {})
    selected_items = _mark_tts_key_lines(items, selection)

    return {
        "vocal_dir": "public/game/vocal",
        "character_voices": character_voices,
        "tts_profile": profile,
        "selection": selection,
        "items": selected_items,
    }


def generate_tts_audio(job_dir: Path, manifest: dict[str, Any], enabled: bool, *, force: bool = False) -> dict[str, Any]:
    profile = manifest.get("tts_profile") or job_tts_profile(job_dir)
    manifest["tts_profile"] = profile
    limits = {**generation_limits().get("tts", {}), **tts_settings(profile)}
    vocal_dir_value = str(manifest.get("vocal_dir") or "public/game/vocal").replace("\\", "/").strip("/")
    if not vocal_dir_value.startswith("public/game/") or ".." in vocal_dir_value.split("/"):
        raise ValueError("TTS vocal_dir must stay under public/game")
    vocal_dir = job_dir / Path(vocal_dir_value)
    vocal_dir.mkdir(parents=True, exist_ok=True)

    items = manifest.get("items", [])
    if not enabled:
        for item in items:
            item["status"] = "skipped_disabled"
        return manifest

    skip_existing = bool(limits.get("skip_existing", True)) and not force
    max_workers = max(1, int(limits.get("max_workers", 4)))

    def synthesize(item: dict[str, Any]) -> dict[str, Any]:
        output = vocal_dir / item["filename"]
        options = options_from_profile(
            profile,
            voice=str(item.get("voice") or _default_voice(profile)),
            instructions=_tts_instructions(item),
        )
        if skip_existing and cached_synthesis(output, str(item["text"]), options):
            item["status"] = "skipped_existing"
            return item
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

    synth_items = [item for item in items if item.get("status") == "pending"]
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(synthesize, item) for item in synth_items]
        for future in as_completed(futures):
            future.result()

    return manifest


def available_tts_voices(profile: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """Return the configured voice library in stable display order."""
    selected = profile or default_tts_profile()
    return [
        {
            "name": voice["id"], "label": voice["label"],
            "gender": voice["gender"], "description": voice["description"],
        }
        for gender in ("male", "female")
        for voice in selected["voices"] if voice["gender"] == gender
    ]


def build_tts_voice_review(
    job_dir: Path,
    character_voices: dict[str, list[str]],
    existing_review: dict[str, Any] | None = None,
    script_text: str | None = None,
) -> dict[str, Any]:
    """Build one representative preview line per narrative character.

    Only speakers declared as characters in the narrative plan are included, so
    narrator/system lines never enter the review.
    """
    profile = job_tts_profile(job_dir)
    narrative_plan = read_json(job_dir / "state" / "narrative_plan.json")
    if script_text is None:
        script_text = (job_dir / "state" / "game_design_webgal.txt").read_text(encoding="utf-8")
    characters = _character_lookup(narrative_plan)
    sanitized_voices = _sanitize_character_voices(narrative_plan, character_voices, profile)
    existing_by_speaker = {
        str(item.get("speaker") or ""): item
        for item in (existing_review or {}).get("characters", [])
        if isinstance(item, dict)
    }

    dialogue_by_speaker: dict[str, list[dict[str, Any]]] = {name: [] for name in characters}
    for scene_name, body in _scene_sections(script_text):
        for line_no, line in enumerate(body.splitlines(), start=1):
            dialogue = _parse_dialogue_line(line)
            if not dialogue:
                continue
            speaker, text = dialogue
            if speaker in dialogue_by_speaker:
                dialogue_by_speaker[speaker].append({"scene": scene_name, "line_no": line_no, "text": text})

    review_items: list[dict[str, Any]] = []
    for speaker, character in characters.items():
        candidates = dialogue_by_speaker.get(speaker, [])
        if not candidates:
            continue
        preview_line = max(candidates, key=_preview_line_score)
        speaker_id = _safe_filename(str(character.get("id") or speaker))
        suggested_voice, suggested_tone = sanitized_voices[speaker]
        previous = existing_by_speaker.get(speaker, {})
        previous_voice = str(previous.get("voice") or "").strip()
        voice = previous_voice if _voice_matches_gender(previous_voice, character.get("gender"), profile) else suggested_voice
        tone = str(previous.get("tone") or suggested_tone).strip()
        filename = _preview_filename(speaker_id, voice)
        review_items.append(
            {
                "speaker": speaker,
                "speaker_id": speaker_id,
                "gender": character.get("gender", ""),
                "voice": voice,
                "tone": tone,
                "scene": preview_line["scene"],
                "line_no": preview_line["line_no"],
                "text": preview_line["text"],
                "filename": filename,
                "status": "pending",
                "error": None,
            }
        )

    return {
        "vocal_dir": "public/game/vocal_preview",
        "available_voices": available_tts_voices(profile),
        "tts_profile": profile,
        "characters": review_items,
    }


def generate_tts_voice_previews(
    job_dir: Path,
    review: dict[str, Any],
    speakers: set[str] | None = None,
    *, force: bool = False,
) -> dict[str, Any]:
    items = review.get("characters", [])
    if not isinstance(items, list):
        raise ValueError("TTS voice review characters must be a list")
    for item in items:
        if not isinstance(item, dict):
            continue
        if speakers is None or str(item.get("speaker") or "") in speakers:
            item["status"] = "pending"
            item["error"] = None
    profile = review.get("tts_profile") or job_tts_profile(job_dir)
    review["tts_profile"] = profile
    manifest = {"vocal_dir": "public/game/vocal_preview", "items": items, "tts_profile": profile}
    generate_tts_audio(job_dir, manifest, enabled=True, force=force)
    return review


def select_tts_review_voice(review: dict[str, Any], speaker: str, voice: str) -> dict[str, Any]:
    profile = review.get("tts_profile") or default_tts_profile()
    if voice not in _valid_voice_names(profile):
        raise ValueError(f"unknown TTS voice: {voice}")
    item = _review_character(review, speaker)
    selected_option = next(
        (option for option in available_tts_voices(profile) if option.get("name") == voice),
        None,
    )
    character_gender = _normalize_gender(item.get("gender"))
    voice_gender = _normalize_gender((selected_option or {}).get("gender"))
    if character_gender in {"male", "female"} and voice_gender != character_gender:
        raise ValueError(f"TTS voice gender does not match character: {speaker}")
    item["voice"] = voice
    if selected_option:
        item["tone"] = str(selected_option.get("description") or "")
    item["filename"] = _preview_filename(str(item.get("speaker_id") or speaker), voice)
    item["status"] = "pending"
    item["error"] = None
    return item


def selected_character_voices(review: dict[str, Any]) -> dict[str, list[str]]:
    items = [item for item in review.get("characters", []) if isinstance(item, dict)]
    return {
        str(item.get("speaker")): [str(item.get("voice") or ""), str(item.get("tone") or "")]
        for item in items
        if str(item.get("speaker") or "").strip()
    }


def _review_character(review: dict[str, Any], speaker: str) -> dict[str, Any]:
    for item in review.get("characters", []):
        if isinstance(item, dict) and str(item.get("speaker") or "") == speaker:
            return item
    raise ValueError(f"character is not available for TTS review: {speaker}")


def _preview_filename(speaker_id: str, voice: str) -> str:
    return f"preview_{_safe_filename(speaker_id)}_{_safe_filename(voice)}.wav"


def _preview_line_score(item: dict[str, Any]) -> int:
    text = str(item.get("text") or "").strip()
    length = len(text)
    score = 100 - abs(length - 22) * 3
    if 8 <= length <= 42:
        score += 40
    elif length < 8:
        score -= 60
    if any(marker in text for marker in ("!", "?", "！", "？", "……")):
        score -= 18
    return score


def _tts_selection(options: dict[str, Any]) -> dict[str, Any]:
    limits = generation_limits().get("tts", {})
    return {
        "scope": "key_lines",
        "max_lines_per_scene": _positive_int(
            options.get("tts_max_lines_per_scene") or limits.get("max_lines_per_scene"),
            3,
        ),
        "max_total_lines": _positive_int(
            options.get("tts_max_total_lines") or limits.get("max_total_lines"),
            60,
        ),
    }


def _mark_tts_key_lines(items: list[dict[str, Any]], selection: dict[str, Any]) -> list[dict[str, Any]]:
    if selection["scope"] == "all":
        for item in items:
            item["is_key_line"] = True
            item["key_line_reason"] = "all_dialogue"
        return items

    selected_ids: set[int] = set()
    per_scene = max(1, int(selection["max_lines_per_scene"]))
    max_total = max(1, int(selection["max_total_lines"]))

    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(str(item.get("scene") or ""), []).append(item)

    for scene_items in grouped.values():
        if not scene_items:
            continue
        chosen: list[dict[str, Any]] = [scene_items[0]]
        if len(scene_items) > 1:
            chosen.append(scene_items[-1])
        middle = [item for item in scene_items[1:-1] if id(item) not in {id(chosen_item) for chosen_item in chosen}]
        middle.sort(key=_key_line_score, reverse=True)
        chosen.extend(middle[: max(0, per_scene - len(chosen))])
        for item in chosen[:per_scene]:
            selected_ids.add(id(item))

    if len(selected_ids) > max_total:
        selected = [item for item in items if id(item) in selected_ids]
        selected.sort(key=_key_line_score, reverse=True)
        selected_ids = {id(item) for item in selected[:max_total]}

    for item in items:
        if id(item) in selected_ids:
            item["is_key_line"] = True
            item["key_line_reason"] = _key_line_reason(item)
        else:
            item["is_key_line"] = False
            item["key_line_reason"] = "not_selected"
            item["status"] = "skipped_non_key"
    return items


def _key_line_score(item: dict[str, Any]) -> int:
    text = str(item.get("text") or "")
    score = min(len(text), 60)
    if any(marker in text for marker in ("？", "?", "！", "!", "为何", "为什么", "难道", "可是", "但", "若", "愿", "必须", "终于")):
        score += 25
    if any(marker in text for marker in ("我", "你", "心", "归", "去", "留", "选择", "决定", "明白", "不愿", "不能")):
        score += 15
    return score


def _key_line_reason(item: dict[str, Any]) -> str:
    text = str(item.get("text") or "")
    if any(marker in text for marker in ("？", "?", "！", "!")):
        return "question_or_exclamation"
    if any(marker in text for marker in ("可是", "但", "若", "愿", "决定", "选择")):
        return "turning_point"
    return "scene_anchor"


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def write_tts_manifest(job_dir: Path, manifest: dict[str, Any]) -> None:
    write_json(job_dir / "state" / "tts_manifest.json", manifest)


def _is_rate_limit_error(error: str) -> bool:
    lowered = error.lower()
    return "rate limit" in lowered or "1007" in lowered or "concurrency" in lowered or "too many requests" in lowered


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
    return scene_sections(script_text)


def _character_lookup(narrative_plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for character in narrative_plan.get("characters", []):
        name = str(character.get("name", "")).strip()
        if name:
            lookup[name] = character
    return lookup


def _character_voice_map(narrative_plan: dict[str, Any], profile: dict[str, Any] | None = None) -> dict[str, list[str]]:
    voices = tts_settings(profile or default_tts_profile()).get("voices", {})
    male_voices = _voice_pool(voices.get("male"), [_default_voice(profile)])
    female_voices = _voice_pool(voices.get("female"), [_default_voice(profile)])
    fallback = str(voices.get("default") or _default_voice(profile))
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


def _sanitize_character_voices(narrative_plan: dict[str, Any], character_voices: dict[str, list[str]], profile: dict[str, Any] | None = None) -> dict[str, list[str]]:
    valid_voices = _valid_voice_names(profile)
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
        if voice not in valid_voices or not _voice_matches_gender(voice, character.get("gender"), profile):
            voice = _fallback_voice_for_gender(character.get("gender"), profile)
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


def _default_voice(profile: dict[str, Any] | None = None) -> str:
    voices = tts_settings(profile or default_tts_profile()).get("voices", {})
    default = str(voices.get("default") or "").strip()
    if default and default in _valid_voice_names(profile):
        return default
    for voice in _voice_names_in_config_order(profile):
        return voice
    return "Cherry"


def _fallback_voice_for_gender(gender_value: Any, profile: dict[str, Any] | None = None) -> str:
    voices = tts_settings(profile or default_tts_profile()).get("voices", {})
    gender = _normalize_gender(gender_value)
    if gender == "male":
        return _voice_pool(voices.get("male"), [_default_voice(profile)])[0]
    if gender == "female":
        return _voice_pool(voices.get("female"), [_default_voice(profile)])[0]
    return _default_voice(profile)


def _voice_matches_gender(voice: str, gender_value: Any, profile: dict[str, Any] | None = None) -> bool:
    if voice not in _valid_voice_names(profile):
        return False
    character_gender = _normalize_gender(gender_value)
    if character_gender not in {"male", "female"}:
        return True
    option = next((item for item in available_tts_voices(profile) if item.get("name") == voice), None)
    return _normalize_gender((option or {}).get("gender")) == character_gender


def _valid_voice_names(profile: dict[str, Any] | None = None) -> set[str]:
    return set(_voice_names_in_config_order(profile))


def _voice_names_in_config_order(profile: dict[str, Any] | None = None) -> list[str]:
    voices = tts_settings(profile or default_tts_profile()).get("voices", {})
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
