from __future__ import annotations

import json
from types import SimpleNamespace

from webgal_backend.pipeline import WebGALPipeline


def test_load_sound_effect_assets_marks_missing_directory_unavailable(tmp_path, monkeypatch):
    pipeline = WebGALPipeline()
    sound_dir = tmp_path / "missing-sounds"
    monkeypatch.setattr(
        "webgal_backend.pipeline.settings",
        SimpleNamespace(sound_effects_dir=sound_dir, workspace_root=tmp_path),
    )

    backend_dir = tmp_path / "webgal_backend"
    backend_dir.mkdir(parents=True, exist_ok=True)
    (backend_dir / "sound_effect_assets.json").write_text(
        json.dumps([{"filename": "rain.mp3", "category": "ambient"}], ensure_ascii=False),
        encoding="utf-8",
    )

    assets = pipeline._load_sound_effect_assets()

    assert assets == [{"filename": "rain.mp3", "category": "ambient", "available": False}]


def test_normalize_sound_effect_plan_ignores_unavailable_assets():
    pipeline = WebGALPipeline()
    plan = pipeline._normalize_sound_effect_plan(
        [{"anchor": "雨声敲在窗沿", "asset": "rain.mp3", "category": "ambient", "operation": "start", "playback": "loop"}],
        [{"filename": "rain.mp3", "available": False}],
    )

    assert plan == []
