from copy import deepcopy

import pytest

from webgal_backend.choice_responses import lower_choice_responses
from webgal_backend.game_design import normalize_completed_json, render_json
from webgal_backend.script_compiler import ScriptCompileError, compile_webgal_script
from webgal_backend.scene_validation import _remove_unreachable_scene_tail


def design(mixed=True):
    return {"scenes": [
        {"scene_file": "start.txt", "lines": [
            {"id": "choice_main", "kind": "choice", "choices": [
                {"id": "stay", "text": "留下", "target": "continue_choice_main" if mixed else "next.txt", "response_lines": [
                    {"id": "stay_line", "kind": "dialogue", "speaker": "甲", "text": "留下专属对白"}]},
                {"id": "leave", "text": "离开", "target": "next.txt", "response_lines": [
                    {"id": "leave_line", "kind": "narration", "text": "离开专属旁白"}]}]},
            *([{"kind": "branch", "text": "continue_choice_main"}, {"kind": "narration", "text": "公共正文"},
               {"kind": "command", "text": "changeScene:next.txt;"}] if mixed else [])]},
        {"scene_file": "next.txt", "marker": "Ending", "lines": [{"kind": "narration", "text": "终点"}]}]}


def compile_design(value):
    return compile_webgal_script(value, {"characters": []}, {"images": []}).script


def follow(script, option):
    """Walk the emitted WebGAL control flow, rather than checking text alone."""
    lines = script.split("Ending:")[0].splitlines()
    labels = {line[6:-1]: i for i, line in enumerate(lines) if line.startswith("label:")}
    seen = []
    index = 0
    for _ in range(100):
        if index >= len(lines):
            break
        line = lines[index]
        if line.startswith("choose:"):
            target = line[7:-1].split("|")[option].rsplit(":", 1)[1]
            index = labels[target]
        elif line.startswith("jumpLabel:"):
            index = labels[line[10:-1]]
        elif line.startswith("changeScene:"):
            return seen, line[12:-1]
        elif line.startswith(("甲:", "旁白:")):
            seen.append(line.split(":", 1)[1].rstrip(";"))
        index += 1
    raise AssertionError("No scene exit reached")


def test_mixed_options_execute_only_their_own_response_and_exit():
    script = compile_design(design())
    assert follow(script, 0) == (["留下专属对白", "公共正文"], "next.txt")
    assert follow(script, 1) == (["离开专属旁白"], "next.txt")


def test_same_destination_keeps_both_responses():
    value = design(False)
    for option in value["scenes"][0]["lines"][0]["choices"]:
        option["text"] = "相同文字，相同目的地"
    script = compile_design(value)
    assert follow(script, 0) == (["留下专属对白"], "next.txt")
    assert follow(script, 1) == (["离开专属旁白"], "next.txt")


def test_empty_response_option_still_has_explicit_exit():
    value = design()
    value["scenes"][0]["lines"][0]["choices"][1]["response_lines"] = []
    assert follow(compile_design(value), 1) == ([], "next.txt")


def test_normalization_rendering_and_compilation_keep_content_and_stable_labels():
    value = normalize_completed_json(design())
    before = deepcopy(value)
    first = lower_choice_responses(value["scenes"][0]["lines"], "start.txt")
    options = value["scenes"][0]["lines"][0]["choices"]
    options.reverse()
    options[0]["text"] = "修改显示文字"
    second = lower_choice_responses(value["scenes"][0]["lines"], "start.txt")
    assert {item["id"] for item in first if str(item.get("id", "")).startswith("response_")} == {
        item["id"] for item in second if str(item.get("id", "")).startswith("response_")}
    assert "留下专属对白" in render_json(before)
    assert "离开专属旁白" in compile_design(value)


@pytest.mark.parametrize("invalid", [[{"kind": "command", "text": "end;"}], [{"kind": "dialogue", "text": " "}], "wrong-type"])
def test_invalid_response_is_rejected(invalid):
    value = design()
    value["scenes"][0]["lines"][0]["choices"][0]["response_lines"] = invalid
    with pytest.raises(ScriptCompileError):
        compile_design(value)


def test_missing_exit_and_duplicate_option_ids_are_rejected():
    value = design(False)
    options = value["scenes"][0]["lines"][0]["choices"]
    options[0]["target"] = "missing.txt"
    with pytest.raises(ScriptCompileError, match="missing response exit"):
        compile_design(value)
    options[0]["target"] = "next.txt"
    options[1]["id"] = options[0]["id"]
    with pytest.raises(ScriptCompileError, match="duplicate"):
        compile_design(value)


def test_repair_preserves_other_branches_and_public_continuation():
    script = compile_design(design())
    lines = script.split("\n\nEnding:")[0].splitlines()[1:]
    repaired, fixes = _remove_unreachable_scene_tail(lines, "start.txt")
    assert repaired == lines
    assert fixes == []


def test_all_external_options_cannot_hide_following_authored_content():
    value = design(False)
    value["scenes"][0]["lines"].append({"kind": "narration", "text": "不可达正文"})
    with pytest.raises(ScriptCompileError, match="final line"):
        compile_design(value)


def test_two_choice_groups_continue_then_leave_without_losing_responses():
    value = design()
    first = value["scenes"][0]["lines"][0]
    for option in first["choices"]:
        option["target"] = "continue_choice_main"
    final = deepcopy(design(False)["scenes"][0]["lines"][0])
    final["id"] = "second_choice"
    value["scenes"][0]["lines"][-1] = final
    script = compile_design(value)
    assert script.count("choose:") == 2
    # Existing per-group option IDs remain scoped to their owning choice.
    assert script.count("留下专属对白") == 2
    assert script.count("离开专属旁白") == 2


def test_pipeline_scene_repair_routes_and_tts_include_response_dialogue(tmp_path):
    from webgal_backend.pipeline import WebGALPipeline
    from webgal_backend.storage import JobStore, write_json
    from webgal_backend.scene_connections import check_scene_connections
    from webgal_backend.scene_validation import _repair_scene_lines
    from webgal_backend.tts_pipeline import build_tts_manifest

    store = JobStore(tmp_path / "jobs")
    job = store.create("choice response integration")
    root = store.job_dir(job["id"])
    plan = {"characters": [{"id": "hero", "name": "甲"}]}
    write_json(root / "state" / "narrative_plan.json", plan)
    write_json(root / "state" / "game_design_completed.json", design())
    write_json(root / "assets_manifest.json", {"images": []})
    pipeline = WebGALPipeline(store=store, llm_factory=lambda **kwargs: pytest.fail("LLM must not compile responses"))
    pipeline.run_script_rewrite(job)
    script = (root / "state" / "game_design_webgal.txt").read_text(encoding="utf-8")
    pipeline._split_game_design_completed_to_scene_files(root, script)
    path = root / "public" / "game" / "scene" / "start.txt"
    repaired, _, _ = _repair_scene_lines(path.read_text(encoding="utf-8").splitlines(), "public/game/scene/start.txt", {}, {}, {"甲"})
    assert "留下专属对白" in "\n".join(repaired)
    assert "离开专属旁白" in "\n".join(repaired)
    path.write_text("\n".join(repaired), encoding="utf-8")
    report = check_scene_connections(root, current_routes=True)
    assert report["status"] == "passed", report
    manifest = build_tts_manifest(root)
    assert any(item["text"] == "留下专属对白" for item in manifest["items"])


def test_response_text_cannot_inject_additional_script_commands():
    value = design(False)
    value["scenes"][0]["lines"][0]["choices"][0]["response_lines"][0]["text"] = "正文;\nchangeScene:missing.txt;"
    for script in (compile_design(value), render_json(value)):
        assert "\nchangeScene:missing.txt;" not in script
        assert "正文； changeScene:missing.txt；" in script


def test_branch_repair_reestablishes_same_speakers_avatar_at_each_entry():
    from webgal_backend.scene_validation import _repair_scene_lines
    value = design(False)
    value["scenes"][0]["lines"][0]["choices"][1]["response_lines"] = [
        {"id": "second", "kind": "dialogue", "speaker": "甲", "text": "另一条对白"}]
    lines = compile_design(value).split("\n\nEnding:")[0].splitlines()[1:]
    repaired, _, _ = _repair_scene_lines(lines, "public/game/scene/start.txt", {"甲": "hero.webp"}, {}, {"甲"})
    assert repaired.count("miniAvatar:hero.webp;") == 2


def test_equal_published_draft_still_rebuilds_old_worker_output(tmp_path):
    from webgal_backend.pipeline import WebGALPipeline
    from webgal_backend.storage import JobStore, write_json

    store = JobStore(tmp_path / "jobs")
    job = store.create("old worker regression")
    root = store.job_dir(job["id"])
    write_json(root / "state" / "game_design_completed.json", design())
    write_json(root / "state" / "published_game_design_completed.json", design())
    write_json(root / "state" / "script_compile_plan.json", {"compiler": "deterministic-webgal-v1"})
    pipeline = WebGALPipeline(store=store)
    assert pipeline._changed_scene_files(root) == {"start.txt"}
    compiled = compile_webgal_script(design(), {"characters": []}, {"images": []})
    write_json(root / "state" / "script_compile_plan.json", compiled.plan)
    path = root / "public" / "game" / "scene" / "start.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(compiled.script.split("\n\nEnding:")[0], encoding="utf-8")
    assert pipeline._changed_scene_files(root) == set()
    path.write_text("choose:留下:next.txt;", encoding="utf-8")
    assert pipeline._changed_scene_files(root) == {"start.txt"}
