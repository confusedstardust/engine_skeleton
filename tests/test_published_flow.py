import json
from webgal_backend.published_flow import published_flow


def test_published_routes_not_draft(tmp_path):
    root = tmp_path / "public/game/scene"
    root.mkdir(parents=True)
    (root / "start.txt").write_text("choose:继续:resume|结束:ending_true.txt;\nlabel:resume;\n旁白;\nchangeScene:phase1.txt;\nchangeScene:obsolete.txt;", encoding="utf-8")
    (root / "phase1.txt").write_text("end;", encoding="utf-8")
    (root / "ending_true.txt").write_text("end;", encoding="utf-8")
    state = tmp_path / "state"
    state.mkdir()
    (state / "published_game_design_completed.json").write_text(json.dumps({"scenes": [{"scene_file": "start.txt", "title": "发布起点"}]}), encoding="utf-8")
    graph = published_flow(tmp_path, 3)
    assert graph["revision"] == 3
    assert graph["nodes"][0]["label"] == "发布起点"
    assert {edge["target"] for edge in graph["edges"]} == {"phase1.txt", "ending_true.txt"}
    assert graph["warnings"] == []


def test_building_reads_last_release_backup(tmp_path):
    for folder, target in [("public/game/scene", "draft.txt"), ("state/published_game_backup/scene", "release.txt")]:
        root = tmp_path / folder
        root.mkdir(parents=True)
        (root / "start.txt").write_text(f"changeScene:{target};", encoding="utf-8")
        (root / target).write_text("end;", encoding="utf-8")
    assert published_flow(tmp_path)["edges"][0]["target"] == "release.txt"


def test_missing_target_visible(tmp_path):
    root = tmp_path / "public/game/scene"
    root.mkdir(parents=True)
    (root / "start.txt").write_text("changeScene:missing.txt;", encoding="utf-8")
    graph = published_flow(tmp_path)
    assert graph["nodes"][-1]["kind"] == "missing"
    assert graph["warnings"]
