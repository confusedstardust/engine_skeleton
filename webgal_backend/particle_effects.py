from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from PIL import Image

from .storage import read_json, write_json


STATE_FILE = "particle_effects.json"
PUBLISHED_STATE_FILE = "published_particle_effects.json"
SCENE_FILE_RE = re.compile(r"^[A-Za-z0-9_-]+\.txt$")

EFFECT_PRESETS: dict[str, dict[str, Any]] = {
    "meteor": {
        "id": "meteor",
        "label": "流星",
        "description": "橙金色流星从右上划向左下，适合夜空、危机和转场。",
        "asset": "meteor.png",
        "count": 18,
        "speed": 16.0,
        "scale": 0.55,
        "angle": 135.0,
        "opacity": 0.95,
        "drift": 0.0,
        "gravity": 0.0,
        "rotation_speed": 0.0,
        "layer": "foreground",
        "blend_mode": "add",
    },
    "wind": {
        "id": "wind",
        "label": "风",
        "description": "青蓝色风痕横向掠过，适合旷野、速度感与情绪流动。",
        "asset": "wind.png",
        "count": 22,
        "speed": 9.0,
        "scale": 0.42,
        "angle": 8.0,
        "opacity": 0.58,
        "drift": 0.4,
        "gravity": 0.0,
        "rotation_speed": 0.002,
        "layer": "foreground",
        "blend_mode": "screen",
    },
    "lightning": {
        "id": "lightning",
        "label": "闪电",
        "description": "蓝紫电弧与分叉闪光，适合风暴、异能和强烈冲突。",
        "asset": "lightning.png",
        "count": 8,
        "speed": 4.0,
        "scale": 0.68,
        "angle": 92.0,
        "opacity": 0.88,
        "drift": 0.0,
        "gravity": 0.0,
        "rotation_speed": 0.004,
        "layer": "foreground",
        "blend_mode": "add",
    },
}

NUMERIC_LIMITS = {
    "count": (1, 300),
    "speed": (0.2, 40.0),
    "scale": (0.05, 2.0),
    "angle": (-180.0, 180.0),
    "opacity": (0.05, 1.0),
    "drift": (-8.0, 8.0),
    "gravity": (-3.0, 3.0),
    "rotation_speed": (-0.1, 0.1),
}


class ParticleEffectError(ValueError):
    pass


def default_state() -> dict[str, Any]:
    return {"version": 1, "scene_effects": {}}


def load_state(job_dir: Path) -> dict[str, Any]:
    path = job_dir / "state" / STATE_FILE
    if not path.exists():
        return default_state()
    payload = read_json(path)
    if not isinstance(payload, dict):
        return default_state()
    return {
        "version": 1,
        "scene_effects": payload.get("scene_effects", {}) if isinstance(payload.get("scene_effects"), dict) else {},
    }


def available_effects(job_dir: Path) -> dict[str, dict[str, Any]]:
    return {key: dict(value) for key, value in EFFECT_PRESETS.items()}


def normalize_assignment(raw: dict[str, Any], effects: dict[str, dict[str, Any]]) -> dict[str, Any]:
    effect_id = str(raw.get("effect_id") or "").strip().lower()
    if not effect_id:
        return {}
    if effect_id not in effects:
        raise ParticleEffectError("unknown particle effect")
    preset = effects[effect_id]
    result = {key: preset[key] for key in preset if key not in {"label", "description"}}
    result["effect_id"] = effect_id
    for key, (minimum, maximum) in NUMERIC_LIMITS.items():
        value = raw.get(key, result.get(key))
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise ParticleEffectError(f"{key} must be numeric") from exc
        numeric = max(minimum, min(maximum, numeric))
        result[key] = int(round(numeric)) if key == "count" else round(numeric, 4)
    layer = str(raw.get("layer", result.get("layer", "foreground"))).strip().lower()
    result["layer"] = layer if layer in {"foreground", "background"} else "foreground"
    blend_mode = str(raw.get("blend_mode", result.get("blend_mode", "normal"))).strip().lower()
    result["blend_mode"] = blend_mode if blend_mode in {"normal", "add", "screen"} else "normal"
    return result


def save_scene_assignment(job_dir: Path, scene_file: str, raw: dict[str, Any] | None) -> dict[str, Any]:
    scene_file = Path(scene_file.replace("\\", "/")).name
    if not SCENE_FILE_RE.fullmatch(scene_file):
        raise ParticleEffectError("invalid scene file")
    state = load_state(job_dir)
    assignments = dict(state["scene_effects"])
    if raw and str(raw.get("effect_id") or "").strip():
        assignments[scene_file] = normalize_assignment(raw, available_effects(job_dir))
    else:
        assignments.pop(scene_file, None)
    state["scene_effects"] = assignments
    write_json(job_dir / "state" / STATE_FILE, state)
    return assignments.get(scene_file, {})


def validate_sprite_sheet(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as image:
            image.load()
            if image.format != "PNG":
                raise ParticleEffectError("effect sprite sheet must be PNG")
            if image.size != (1280, 128):
                raise ParticleEffectError("effect sprite sheet must be exactly 1280x128 pixels")
            rgba = image.convert("RGBA")
            alpha = rgba.getchannel("A")
            if alpha.getextrema() == (255, 255):
                raise ParticleEffectError("effect sprite sheet must contain real transparency")
            for index in range(10):
                frame_alpha = alpha.crop((index * 128, 0, (index + 1) * 128, 128))
                if frame_alpha.getbbox() is None:
                    raise ParticleEffectError(f"effect frame {index + 1} is empty")
    except ParticleEffectError:
        raise
    except Exception as exc:
        raise ParticleEffectError("effect sprite sheet is not a valid PNG") from exc
    return 128, 10


def runtime_config(job_dir: Path) -> dict[str, Any]:
    effects = available_effects(job_dir)
    return {
        "version": 1,
        "sheet": {"frame_width": 128, "frame_height": 128, "frame_count": 10, "columns": 10},
        "effects": {effect_id: {**effect, "asset": f"tex/effects/{effect['asset']}"} for effect_id, effect in effects.items()},
    }
