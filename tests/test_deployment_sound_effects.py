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


def test_load_bgm_assets_groups_files_from_sound_effects_directory(tmp_path, monkeypatch):
    sound_dir = tmp_path / "sound-effects"
    sound_dir.mkdir()
    for filename in [
        "Bgm_Opening_main.mp3",
        "Bgm_Dialog001.mp3",
        "Bgm_Dialog002.mp3",
        "Bgm_ending_happy.mp3",
        "door-open.mp3",
    ]:
        (sound_dir / filename).write_bytes(b"mp3")
    monkeypatch.setattr(
        "webgal_backend.pipeline.settings",
        SimpleNamespace(sound_effects_dir=sound_dir, workspace_root=tmp_path),
    )

    assets = WebGALPipeline()._load_bgm_assets()

    assert assets == {
        "opening": ["Bgm_Opening_main.mp3"],
        "dialog": ["Bgm_Dialog001.mp3", "Bgm_Dialog002.mp3"],
        "ending": ["Bgm_ending_happy.mp3"],
    }


def test_bgm_plan_uses_opening_dialog_and_priority_ending_assets():
    pipeline = WebGALPipeline()
    script = "\n".join(
        [
            "Scene:start.txt",
            ":opening;",
            "Scene:chapter_02.txt",
            ":middle;",
            "Ending:ending_true.txt",
            ":true ending;",
            "Ending:ending_failure.txt",
            ":bad ending;",
        ]
    )

    plan = pipeline._build_bgm_plan(
        script,
        {
            "opening": ["Bgm_Opening_main.mp3"],
            "dialog": ["Bgm_Dialog001.mp3"],
            "ending": ["Bgm_ending_bad.mp3", "Bgm_ending_happy.mp3", "Bgm_ending_normal.mp3"],
        },
    )

    assert [item["asset"] for item in plan] == [
        "Bgm_Opening_main.mp3",
        "Bgm_Dialog001.mp3",
        "Bgm_ending_happy.mp3",
        "Bgm_ending_bad.mp3",
    ]
    assert pipeline._select_ending_bgm("ending_1.txt", ["Bgm_ending_happy.mp3"]) == "Bgm_ending_happy.mp3"
    assert pipeline._select_ending_bgm("ending_2.txt", ["Bgm_ending_normal.mp3"]) == "Bgm_ending_normal.mp3"


def test_insert_bgm_adds_commands_after_scene_headers():
    pipeline = WebGALPipeline()
    script = "\n".join(["Scene:start.txt", ":opening;", "Scene:chapter_02.txt", ":middle;"])

    inserted, report = pipeline._insert_bgm(
        script,
        [
            {"line_index": 1, "asset": "Bgm_Opening_main.mp3", "role": "opening", "scene_file": "start.txt"},
            {"line_index": 3, "asset": "Bgm_Dialog001.mp3", "role": "dialog", "scene_file": "chapter_02.txt"},
        ],
    )

    assert inserted.splitlines() == [
        "Scene:start.txt",
        "bgm:Bgm_Opening_main.mp3 -volume=45 -enter=1500;",
        ":opening;",
        "Scene:chapter_02.txt",
        "bgm:Bgm_Dialog001.mp3 -volume=45 -enter=1500;",
        ":middle;",
    ]
    assert [item["asset"] for item in report["inserted"]] == ["Bgm_Opening_main.mp3", "Bgm_Dialog001.mp3"]


def test_copy_bgm_files_uses_game_bgm_directory(tmp_path, monkeypatch):
    sound_dir = tmp_path / "sound-effects"
    sound_dir.mkdir()
    (sound_dir / "Bgm_Opening_main.mp3").write_bytes(b"opening")
    monkeypatch.setattr(
        "webgal_backend.pipeline.settings",
        SimpleNamespace(sound_effects_dir=sound_dir, workspace_root=tmp_path),
    )
    job_dir = tmp_path / "job"

    WebGALPipeline()._copy_bgm_files(
        job_dir,
        {"inserted": [{"asset": "Bgm_Opening_main.mp3"}]},
    )

    assert (job_dir / "public" / "game" / "bgm" / "Bgm_Opening_main.mp3").read_bytes() == b"opening"
