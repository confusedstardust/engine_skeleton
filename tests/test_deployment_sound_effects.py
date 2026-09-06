from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from webgal_backend.pipeline import WebGALPipeline
from webgal_backend.storage import JobStore, write_json


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


def test_apply_music_draft_updates_only_selected_scene_without_script_rewrite(tmp_path, monkeypatch):
    sound_dir = tmp_path / "sound-effects"
    sound_dir.mkdir()
    (sound_dir / "Bgm_Opening_ordinary.mp3").write_bytes(b"system")
    (sound_dir / "Bgm_ending_bad.mp3").write_bytes(b"selected")
    monkeypatch.setattr(
        "webgal_backend.pipeline.settings",
        SimpleNamespace(sound_effects_dir=sound_dir, workspace_root=tmp_path),
    )

    store = JobStore(tmp_path / "jobs")
    job = store.create("source")
    job_dir = store.job_dir(job["id"])
    game_dir = job_dir / "public" / "game"
    (game_dir / "config.txt").write_text("Game_name:test;\n", encoding="utf-8")
    scene_dir = game_dir / "scene"
    scene_dir.mkdir(parents=True, exist_ok=True)
    start = scene_dir / "start.txt"
    other = scene_dir / "phase2.txt"
    start.write_text("bgm:Bgm_Opening_ordinary.mp3 -volume=45 -enter=1500;\n主角:开始;\n", encoding="utf-8")
    other.write_text("bgm:Bgm_Dialog001.mp3 -volume=45 -enter=1500;\n主角:继续;\n", encoding="utf-8")
    write_json(job_dir / "state" / "scene_plan.json", {"scenes": [{"scene_file": "start.txt"}, {"scene_file": "phase2.txt"}], "endings": []})
    write_json(job_dir / "state" / "scene_music_overrides.json", {"version": 1, "scene_overrides": {}})
    store.mark_build_complete(job)

    pipeline = WebGALPipeline(store)
    pipeline._snapshot_published_edit_state(job_dir)
    write_json(job_dir / "state" / "scene_music_overrides.json", {"version": 1, "scene_overrides": {"start.txt": "Bgm_ending_bad.mp3"}})
    store.mark_draft_changed(job, "music")
    monkeypatch.setattr(pipeline, "run_script_rewrite", lambda _job: pytest.fail("music-only sync must not rewrite scripts"))
    monkeypatch.setattr(pipeline, "run_validation", lambda _job: None)

    pipeline.apply_draft_changes(store.get(job["id"]))

    assert start.read_text(encoding="utf-8").splitlines()[0] == "bgm:Bgm_ending_bad.mp3 -volume=45 -enter=1500;"
    assert other.read_text(encoding="utf-8") == "bgm:Bgm_Dialog001.mp3 -volume=45 -enter=1500;\n主角:继续;\n"
    assert (game_dir / "bgm" / "Bgm_ending_bad.mp3").read_bytes() == b"selected"
    assert store.get(job["id"])["build_state"] == "CURRENT"


def test_apply_scene_draft_writes_only_changed_scene_file(tmp_path, monkeypatch):
    store = JobStore(tmp_path / "jobs")
    job = store.create("source")
    job_dir = store.job_dir(job["id"])
    game_dir = job_dir / "public" / "game"
    (game_dir / "config.txt").write_text("Game_name:test;\n", encoding="utf-8")
    scene_dir = game_dir / "scene"
    scene_dir.mkdir(parents=True, exist_ok=True)
    start = scene_dir / "start.txt"
    other = scene_dir / "phase2.txt"
    start.write_text("主角:旧开场;\n", encoding="utf-8")
    other.write_text("主角:未修改;\n", encoding="utf-8")
    original_design = {
        "version": 1,
        "scenes": [
            {"scene_file": "start.txt", "lines": [{"kind": "dialogue", "speaker": "主角", "text": "旧开场"}]},
            {"scene_file": "phase2.txt", "lines": [{"kind": "dialogue", "speaker": "主角", "text": "未修改"}]},
        ],
    }
    write_json(job_dir / "state" / "game_design_completed.json", original_design)
    write_json(job_dir / "state" / "scene_music_overrides.json", {"version": 1, "scene_overrides": {}})
    store.mark_build_complete(job)

    pipeline = WebGALPipeline(store)
    pipeline._snapshot_published_edit_state(job_dir)
    changed_design = json.loads(json.dumps(original_design, ensure_ascii=False))
    changed_design["scenes"][0]["lines"][0]["text"] = "新开场"
    write_json(job_dir / "state" / "game_design_completed.json", changed_design)
    store.mark_draft_changed(job, "scenes")

    def fake_rewrite(_job):
        (job_dir / "state" / "game_design_webgal.txt").write_text(
            "Scene:start.txt\n主角:新开场;\n\nScene:phase2.txt\n主角:模型不应覆盖这一场;\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(pipeline, "run_script_rewrite", fake_rewrite)
    monkeypatch.setattr(pipeline, "run_sound_effects", lambda _job: None)
    monkeypatch.setattr(pipeline, "run_tts_generation", lambda _job: None)
    monkeypatch.setattr(pipeline, "run_validation", lambda _job: None)

    pipeline.apply_draft_changes(store.get(job["id"]))

    assert start.read_text(encoding="utf-8") == "主角:新开场;\n"
    assert other.read_text(encoding="utf-8") == "主角:未修改;\n"
    assert store.get(job["id"])["dirty_scopes"] == []


def test_failed_draft_apply_restores_current_playable_game(tmp_path, monkeypatch):
    store = JobStore(tmp_path / "jobs")
    job = store.create("source")
    job_dir = store.job_dir(job["id"])
    game_dir = job_dir / "public" / "game"
    (game_dir / "config.txt").write_text("Game_name:test;\n", encoding="utf-8")
    published_asset = game_dir / "background" / "room.webp"
    published_asset.parent.mkdir(parents=True, exist_ok=True)
    published_asset.write_bytes(b"published")
    draft_asset = job_dir / "draft" / "game" / "background" / "room.webp"
    draft_asset.parent.mkdir(parents=True, exist_ok=True)
    draft_asset.write_bytes(b"draft")
    store.mark_build_complete(job)
    store.mark_draft_changed(job, "assets")
    pipeline = WebGALPipeline(store)
    monkeypatch.setattr(pipeline, "run_validation", lambda _job: (_ for _ in ()).throw(RuntimeError("validation failed")))

    with pytest.raises(RuntimeError, match="validation failed"):
        pipeline.apply_draft_changes(store.get(job["id"]))

    assert published_asset.read_bytes() == b"published"
    assert store.get(job["id"])["build_state"] == "FAILED"


def test_apply_voice_draft_regenerates_audio_without_rewriting_scenes(tmp_path, monkeypatch):
    store = JobStore(tmp_path / "jobs")
    job = store.create("source")
    job_dir = store.job_dir(job["id"])
    (job_dir / "public" / "game" / "config.txt").write_text("Game_name:test;\n", encoding="utf-8")
    store.mark_build_complete(job)
    store.mark_draft_changed(job, "voices")
    pipeline = WebGALPipeline(store)
    calls: list[str] = []
    monkeypatch.setattr(pipeline, "run_script_rewrite", lambda _job: pytest.fail("voice-only sync must not rewrite scenes"))
    monkeypatch.setattr(pipeline, "run_tts_generation", lambda _job: calls.append("tts"))
    monkeypatch.setattr(pipeline, "run_validation", lambda _job: None)

    pipeline.apply_draft_changes(store.get(job["id"]))

    assert calls == ["tts"]
    assert store.get(job["id"])["build_state"] == "CURRENT"
