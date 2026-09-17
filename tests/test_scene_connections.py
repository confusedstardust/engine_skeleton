from __future__ import annotations

import pytest

from webgal_backend.pipeline import WebGALPipeline
from webgal_backend.scene_connections import check_scene_connections
from webgal_backend.scene_plan import build_scene_plan
from webgal_backend.storage import JobStore, read_json, write_json


def prepare_scenes(tmp_path, structure, steps, endings):
    job_dir = tmp_path / "job"
    state_dir = job_dir / "state"
    scene_dir = job_dir / "public" / "game" / "scene"
    state_dir.mkdir(parents=True)
    scene_dir.mkdir(parents=True)
    narrative = {
        "story_progression": [{"id": node_id, "name": node_id} for node_id in steps],
        "endings": [{"ending_type": ending_type} for ending_type in endings],
        "narrative_structure": structure,
    }
    write_json(state_dir / "narrative_plan.json", narrative)
    write_json(state_dir / "scene_plan.json", build_scene_plan(narrative))
    return job_dir, scene_dir


def test_single_next_scene_is_appended_once_and_reachable(tmp_path):
    job_dir, scene_dir = prepare_scenes(tmp_path, "flowchart TD\n start_node --> phase1\n phase1 --> ending_1", ["start_node", "phase1"], ["ending_1"])
    start = scene_dir / "start.txt"
    start.write_text("主角:开场;\n", encoding="utf-8")
    (scene_dir / "phase1.txt").write_text("主角:下一幕;\nchangeScene:ending_1.txt;\n", encoding="utf-8")
    (scene_dir / "ending_1.txt").write_text("主角:结束;\nend;\n", encoding="utf-8")

    report = check_scene_connections(job_dir)
    repeated = check_scene_connections(job_dir)

    assert report["status"] == "passed"
    assert start.read_text(encoding="utf-8").endswith("changeScene:phase1.txt;\n")
    assert [fix["code"] for fix in report["fixes"]] == ["append_change_scene"]
    assert repeated["fixes"] == []
    assert report["reachable"] == ["ending_1.txt", "phase1.txt", "start.txt"]


def test_external_choices_preserve_all_flowchart_branches(tmp_path):
    structure = "flowchart TD\n start_node --> phase1\n start_node --> phase2\n phase1 --> ending_1\n phase2 --> ending_1"
    job_dir, scene_dir = prepare_scenes(tmp_path, structure, ["start_node", "phase1", "phase2"], ["ending_1"])
    choice = "choose:立刻走:phase1.txt|再想想:phase2.txt;\n"
    (scene_dir / "start.txt").write_text(choice, encoding="utf-8")
    (scene_dir / "phase1.txt").write_text("changeScene:ending_1.txt;\n", encoding="utf-8")
    (scene_dir / "phase2.txt").write_text("changeScene:ending_1.txt;\n", encoding="utf-8")
    (scene_dir / "ending_1.txt").write_text("end;\n", encoding="utf-8")

    report = check_scene_connections(job_dir)

    assert report["status"] == "passed"
    assert report["fixes"] == []
    assert (scene_dir / "start.txt").read_text(encoding="utf-8") == choice


def test_multiple_next_scenes_without_choice_report_error(tmp_path):
    structure = "flowchart TD\n start_node --> phase1\n start_node --> phase2"
    job_dir, scene_dir = prepare_scenes(tmp_path, structure, ["start_node", "phase1", "phase2"], [])
    start = scene_dir / "start.txt"
    start.write_text("主角:选哪条路?;\n", encoding="utf-8")
    (scene_dir / "phase1.txt").write_text("主角:一;\n", encoding="utf-8")
    (scene_dir / "phase2.txt").write_text("主角:二;\n", encoding="utf-8")

    report = check_scene_connections(job_dir)

    assert report["status"] == "failed"
    assert any(error["code"] == "missing_branch_choice" and error["scene_file"] == "start.txt" for error in report["errors"])
    assert "changeScene:" not in start.read_text(encoding="utf-8")


def test_wrong_existing_jump_is_reported_without_replacement(tmp_path):
    structure = "flowchart TD\n start_node --> phase1\n phase1 --> ending_1"
    job_dir, scene_dir = prepare_scenes(tmp_path, structure, ["start_node", "phase1"], ["ending_1"])
    start = scene_dir / "start.txt"
    start.write_text("changeScene:ending_1.txt;\n", encoding="utf-8")
    (scene_dir / "phase1.txt").write_text("changeScene:ending_1.txt;\n", encoding="utf-8")
    (scene_dir / "ending_1.txt").write_text("end;\n", encoding="utf-8")

    report = check_scene_connections(job_dir)

    assert any(error["code"] == "flow_target_mismatch" and error["scene_file"] == "start.txt" for error in report["errors"])
    assert any(error["code"] == "unreachable_scene" and error["scene_file"] == "phase1.txt" for error in report["errors"])
    assert start.read_text(encoding="utf-8") == "changeScene:ending_1.txt;\n"


def test_failed_graph_check_does_not_commit_other_suggested_jumps(tmp_path):
    structure = "flowchart TD\n start_node --> phase1\n phase1 --> ending_1"
    job_dir, scene_dir = prepare_scenes(tmp_path, structure, ["start_node", "phase1"], ["ending_1"])
    start = scene_dir / "start.txt"
    start.write_text("主角:开场;\n", encoding="utf-8")
    (scene_dir / "phase1.txt").write_text("changeScene:unknown.txt;\n", encoding="utf-8")
    (scene_dir / "ending_1.txt").write_text("end;\n", encoding="utf-8")

    report = check_scene_connections(job_dir)

    assert report["status"] == "failed"
    assert start.read_text(encoding="utf-8") == "主角:开场;\n"
    assert report["fixes"] == []
    assert any(fix["code"] == "append_change_scene" for fix in report["suggested_fixes"])


def test_unknown_flowchart_target_is_not_silently_ignored(tmp_path):
    structure = "flowchart TD\n start_node --> phase1\n start_node --> missing_node\n phase1 --> ending_1"
    job_dir, scene_dir = prepare_scenes(tmp_path, structure, ["start_node", "phase1"], ["ending_1"])
    (scene_dir / "start.txt").write_text("changeScene:phase1.txt;\n", encoding="utf-8")
    (scene_dir / "phase1.txt").write_text("changeScene:ending_1.txt;\n", encoding="utf-8")
    (scene_dir / "ending_1.txt").write_text("end;\n", encoding="utf-8")

    report = check_scene_connections(job_dir)

    assert report["status"] == "failed"
    assert any(error["code"] == "unmapped_flow_edge" for error in report["errors"])


def test_unplanned_scene_file_is_reported(tmp_path):
    job_dir, scene_dir = prepare_scenes(tmp_path, "flowchart TD\n start_node --> ending_1", ["start_node"], ["ending_1"])
    (scene_dir / "start.txt").write_text("changeScene:ending_1.txt;\n", encoding="utf-8")
    (scene_dir / "ending_1.txt").write_text("end;\n", encoding="utf-8")
    (scene_dir / "orphan.txt").write_text("主角:没人会看到;\n", encoding="utf-8")

    report = check_scene_connections(job_dir)

    assert report["status"] == "failed"
    assert any(error["code"] == "unplanned_scene_file" and error["scene_file"] == "orphan.txt" for error in report["errors"])


def test_html_space_after_terminal_choice_is_cleaned(tmp_path):
    job_dir, scene_dir = prepare_scenes(tmp_path, "flowchart TD\n start_node --> phase1\n phase1 --> ending_1", ["start_node", "phase1"], ["ending_1"])
    start = scene_dir / "start.txt"
    start.write_text("choose:接过它:phase1.txt|迟疑一瞬:phase1.txt;&#x20;\n", encoding="utf-8")
    (scene_dir / "phase1.txt").write_text("changeScene:ending_1.txt;\n", encoding="utf-8")
    (scene_dir / "ending_1.txt").write_text("end;\n", encoding="utf-8")

    report = check_scene_connections(job_dir)

    assert report["status"] == "passed"
    assert start.read_text(encoding="utf-8") == "choose:接过它:phase1.txt|迟疑一瞬:phase1.txt;\n"
    assert report["fixes"][0]["code"] == "remove_html_space_after_command"


def test_pipeline_validation_persists_connection_node_after_scene_repair(tmp_path):
    store = JobStore(tmp_path / "jobs")
    job = store.create("source")
    job_dir = store.job_dir(job["id"])
    narrative = {
        "story_progression": [{"id": "start_node"}, {"id": "phase1"}],
        "endings": [{"ending_type": "ending_1"}],
        "narrative_structure": "flowchart TD\n start_node --> phase1\n phase1 --> ending_1",
    }
    write_json(job_dir / "state" / "narrative_plan.json", narrative)
    write_json(job_dir / "state" / "scene_plan.json", build_scene_plan(narrative))
    scene_dir = job_dir / "public" / "game" / "scene"
    (scene_dir / "start.txt").write_text("主角:开场;\nchangeScene:phase1.txt;\n", encoding="utf-8")
    (scene_dir / "phase1.txt").write_text("changeScene:ending_1.txt;\n", encoding="utf-8")
    (scene_dir / "ending_1.txt").write_text("end;\n", encoding="utf-8")

    WebGALPipeline(store).run_validation(job)

    assert read_json(job_dir / "state" / "scene_connection_report.json")["status"] == "passed"
    assert (scene_dir / "start.txt").read_text(encoding="utf-8").endswith("changeScene:phase1.txt;\n")
    assert store.get(job["id"])["artifacts"]["scene_connection_report"] == "state/scene_connection_report.json"


def test_failed_connection_check_blocks_publish_and_keeps_published_scene(tmp_path, monkeypatch):
    store = JobStore(tmp_path / "jobs")
    job = store.create("source")
    job_dir = store.job_dir(job["id"])
    narrative = {
        "story_progression": [{"id": "start_node"}, {"id": "phase1"}],
        "endings": [{"ending_type": "ending_1"}],
        "narrative_structure": "flowchart TD\n start_node --> phase1\n phase1 --> ending_1",
    }
    write_json(job_dir / "state" / "narrative_plan.json", narrative)
    write_json(job_dir / "state" / "scene_plan.json", build_scene_plan(narrative))
    game_dir = job_dir / "public" / "game"
    (game_dir / "config.txt").write_text("Game_name:test;\n", encoding="utf-8")
    scene_dir = game_dir / "scene"
    published_start = "主角:旧开场;\nchangeScene:phase1.txt;\n"
    (scene_dir / "start.txt").write_text(published_start, encoding="utf-8")
    (scene_dir / "phase1.txt").write_text("changeScene:ending_1.txt;\n", encoding="utf-8")
    (scene_dir / "ending_1.txt").write_text("end;\n", encoding="utf-8")
    store.mark_build_complete(job)
    store.mark_draft_changed(job, "scenes")
    pipeline = WebGALPipeline(store)
    monkeypatch.setattr(pipeline, "_changed_scene_files", lambda _job_dir: {"start.txt"})
    monkeypatch.setattr(pipeline, "run_script_rewrite", lambda _job: None)
    monkeypatch.setattr(pipeline, "run_sound_effects", lambda _job: None)
    monkeypatch.setattr(pipeline, "run_tts_generation", lambda _job: None)
    (job_dir / "state" / "game_design_webgal.txt").write_text(
        "Scene:start.txt\n主角:新开场;\n", encoding="utf-8"
    )

    with pytest.raises(RuntimeError, match="scene connection check failed"):
        pipeline.apply_draft_changes(store.get(job["id"]))

    assert (scene_dir / "start.txt").read_text(encoding="utf-8") == published_start
    assert read_json(job_dir / "state" / "scene_connection_report.json")["status"] == "failed"
    assert store.get(job["id"])["build_state"] == "FAILED"


def test_current_routes_check_all_scenes_without_auto_repair(tmp_path):
    job_dir, scene_dir = prepare_scenes(tmp_path, "flowchart TD\n start_node --> phase1", ["start_node", "phase1", "phase2"], [])
    (scene_dir / "start.txt").write_text("changeScene:phase2.txt;\n", encoding="utf-8")
    (scene_dir / "phase1.txt").write_text("旁白:未衔接一;\n", encoding="utf-8")
    (scene_dir / "phase2.txt").write_text("旁白:未衔接二;\n", encoding="utf-8")
    report = check_scene_connections(job_dir, current_routes=True)
    assert {error["scene_file"] for error in report["errors"]} == {"phase1.txt", "phase2.txt"}
    assert report["fixes"] == []
    assert (scene_dir / "phase1.txt").read_text(encoding="utf-8") == "旁白:未衔接一;\n"


def test_current_routes_accept_changed_links_and_choices(tmp_path):
    job_dir, scene_dir = prepare_scenes(tmp_path, "flowchart TD\n start_node --> phase1", ["start_node", "phase1", "phase2"], [])
    (scene_dir / "start.txt").write_text("choose:改走第二幕:phase2.txt|结束:phase1.txt;\n", encoding="utf-8")
    (scene_dir / "phase1.txt").write_text("end;\n", encoding="utf-8")
    (scene_dir / "phase2.txt").write_text("changeScene:phase1.txt;\n", encoding="utf-8")
    assert check_scene_connections(job_dir, current_routes=True)["status"] == "passed"


def test_current_routes_reject_missing_choice_target(tmp_path):
    job_dir, scene_dir = prepare_scenes(tmp_path, "flowchart TD\n start_node --> phase1", ["start_node", "phase1"], [])
    (scene_dir / "start.txt").write_text("choose:继续:missing.txt;\n", encoding="utf-8")
    report = check_scene_connections(job_dir, current_routes=True)
    assert any(error["code"] == "missing_target" for error in report["errors"])
