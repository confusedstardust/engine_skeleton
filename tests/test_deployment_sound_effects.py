from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from webgal_backend.pipeline import WebGALPipeline
from webgal_backend.storage import JobStore


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


def test_bgm_plan_uses_explicit_music_moods_and_semantic_fallbacks():
    pipeline = WebGALPipeline()
    script = "\n".join(["Scene:start.txt", ":opening;", "Ending:ending_1.txt", ":terrible ending;", "Ending:ending_2.txt", ":sad ending;"])
    scene_plan = {
        "scenes": [{"scene_file": "start.txt", "music_mood": "tense"}],
        "endings": [
            {"scene_file": "ending_1.txt", "music_mood": "terrible"},
            {"scene_file": "ending_2.txt", "description": "众人离散，只余遗憾。"},
        ],
    }
    plan = pipeline._build_bgm_plan(
        script,
        {
            "opening": ["Bgm_Opening_ordinary.mp3", "Bgm_Opening_tense.mp3"],
            "dialog": [],
            "ending": ["Bgm_ending_normal.mp3", "Bgm_ending_sad.mp3", "Bgm_ending_terrible.mp3"],
        },
        scene_plan,
    )
    assert [item["asset"] for item in plan] == ["Bgm_Opening_tense.mp3", "Bgm_ending_terrible.mp3", "Bgm_ending_sad.mp3"]
    assert plan[0]["source"] == "scene.music_mood"
    assert plan[2]["source"] == "ending.semantic_fallback"


def test_bgm_plan_uses_user_scene_override_only_when_selected_asset_is_available():
    pipeline = WebGALPipeline()
    plan = pipeline._build_bgm_plan(
        "Scene:start.txt\n:opening;",
        {"opening": ["Bgm_Opening_ordinary.mp3"], "dialog": ["Bgm_Dialog001.mp3"], "ending": []},
        {"scenes": [{"scene_file": "start.txt", "music_mood": "ordinary"}], "endings": []},
        {"start.txt": "Bgm_Dialog001.mp3"},
    )
    assert plan[0]["system_asset"] == "Bgm_Opening_ordinary.mp3"
    assert plan[0]["asset"] == "Bgm_Dialog001.mp3"
    assert plan[0]["source"] == "user.scene_override"

    ignored = pipeline._build_bgm_plan(
        "Scene:start.txt\n:opening;",
        {"opening": ["Bgm_Opening_ordinary.mp3"], "dialog": [], "ending": []},
        {"scenes": [{"scene_file": "start.txt", "music_mood": "ordinary"}], "endings": []},
        {"start.txt": "not-in-library.mp3"},
    )
    assert ignored[0]["asset"] == "Bgm_Opening_ordinary.mp3"
    assert ignored[0]["override"] is False


def test_generate_config_uses_planned_opening_bgm_and_preserves_all_keys(tmp_path):
    pipeline = WebGALPipeline()
    job_dir = tmp_path / "job"
    (job_dir / "state").mkdir(parents=True)
    (job_dir / "public" / "game" / "background").mkdir(parents=True)
    (job_dir / "public" / "game" / "bgm").mkdir(parents=True)
    (job_dir / "public" / "game" / "background" / "opening.webp").write_bytes(b"image")
    (job_dir / "public" / "game" / "bgm" / "Bgm_Opening_warm.mp3").write_bytes(b"music")
    (job_dir / "state" / "bgm_plan.json").write_text(json.dumps([{"role": "opening", "asset": "Bgm_Opening_warm.mp3"}]), encoding="utf-8")
    (job_dir / "job.json").write_text(json.dumps({"source_material": "source"}), encoding="utf-8")
    pipeline._generate_config(job_dir, {"title": "测试游戏", "game_key": "test-key"})
    assert (job_dir / "public" / "game" / "config.txt").read_text(encoding="utf-8").splitlines() == [
        "Game_name:测试游戏;", "Game_key:test-key;", "Title_img:opening.webp;", "Title_bgm:Bgm_Opening_warm.mp3;", "Game_Logo:;"
    ]


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


def test_completed_asset_regeneration_writes_draft_without_touching_published_game(tmp_path, monkeypatch):
    store = JobStore(tmp_path / "jobs")
    job = store.create("source")
    job_dir = store.job_dir(job["id"])
    public_asset = job_dir / "public" / "game" / "background" / "bg_room.webp"
    public_asset.write_bytes(b"published")
    (job_dir / "public" / "game" / "config.txt").write_text("Game_name:test;\n", encoding="utf-8")
    (job_dir / "assets_manifest.json").write_text(json.dumps({"base_dir": str(job_dir / "public" / "game"), "model": "test", "images": [{"filename": "bg_room", "subdir": "background", "size": "1920x1080", "prompt": "old prompt"}]}), encoding="utf-8")
    store.mark_build_complete(job)
    pipeline = WebGALPipeline(store)
    monkeypatch.setattr(pipeline, "_image_generation_config", lambda _job: ("provider", "test"))

    def fake_generate(_job, _job_dir, manifest_path):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        target = Path(manifest["base_dir"]) / "background" / "bg_room.webp"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"draft")

    monkeypatch.setattr(pipeline, "_run_asset_script_manifest", fake_generate)
    pipeline.regenerate_asset_image(store.get(job["id"]), "bg_room", "new prompt")
    assert public_asset.read_bytes() == b"published"
    assert (job_dir / "draft" / "game" / "background" / "bg_room.webp").read_bytes() == b"draft"
    updated = store.get(job["id"])
    assert updated["status"] == "DONE"
    assert updated["build_state"] == "STALE"


def test_failed_rebuild_restores_previous_published_game(tmp_path, monkeypatch):
    store = JobStore(tmp_path / "jobs")
    job = store.create("source")
    job_dir = store.job_dir(job["id"])
    game_dir = job_dir / "public" / "game"
    (game_dir / "config.txt").write_text("Game_name:published;\n", encoding="utf-8")
    marker = game_dir / "scene" / "start.txt"
    marker.write_text("published scene\n", encoding="utf-8")
    store.mark_build_complete(job)
    pipeline = WebGALPipeline(store)

    def fail_after_overwrite(_job):
        marker.write_text("partial rebuild\n", encoding="utf-8")
        raise RuntimeError("build failed")

    monkeypatch.setattr(pipeline, "run_script_rewrite", fail_after_overwrite)
    with pytest.raises(RuntimeError, match="build failed"):
        pipeline.run_game_build(store.get(job["id"]))
    assert marker.read_text(encoding="utf-8") == "published scene\n"
    assert store.get(job["id"])["build_state"] == "FAILED"
