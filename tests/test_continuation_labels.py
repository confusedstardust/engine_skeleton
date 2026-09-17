from copy import deepcopy

from webgal_backend.game_design import normalize_completed_json, repair_continuation_labels
from webgal_backend.script_compiler import compile_webgal_script


def test_missing_editor_label_is_restored_before_authored_narration_and_compiles():
    target = "continue_choice_mu3k9j5e"
    choice = {"id": "old-choice", "kind": "choice", "choices": [{"text": "继续", "target": target}, {"text": "停一下", "target": target}]}
    narration = {"id": "authored", "kind": "narration", "text": "灯油将尽，老翁又到炭车旁站了一会儿，把明天要带的东西数了一遍。"}
    exit_line = {"kind": "choice", "choices": [{"text": "下一幕", "target": "ending_1.txt"}]}
    design = {"version": 1, "scenes": [
        {"scene_file": "start.txt", "marker": "Scene", "lines": [choice, narration, exit_line]},
        {"scene_file": "ending_1.txt", "marker": "Ending", "lines": [{"kind": "narration", "text": "结束"}]},
    ]}
    original = deepcopy(design)
    repaired = repair_continuation_labels(design)
    lines = repaired["scenes"][0]["lines"]
    assert design == original
    assert lines[1]["branchLabel"] == target
    assert lines[2] == narration
    assert lines[0] == choice
    assert lines[-1] == exit_line
    assert repair_continuation_labels(repaired) == repaired
    assert normalize_completed_json(design) == repaired
    script = compile_webgal_script(repaired, {"characters": []}, {"images": []}).script
    assert f"label:{target};\n旁白:{narration['text']};" in script


def test_user_defined_missing_label_is_not_repaired():
    design = {"scenes": [{"lines": [{"kind": "choice", "choices": [{"text": "自定义", "target": "user_label"}]}]}]}
    assert repair_continuation_labels(design) == design


def test_existing_label_is_not_duplicated_or_moved_and_target_aliases_work():
    target = "continue_choice_existing"
    design = {"scenes": [{"lines": [
        {"kind": "choice", "choices": [{"text": "继续", "targetSceneFile": target}]},
        {"kind": "narration", "text": "保留位置"},
        {"kind": "branch", "text": target, "branchLabel": target},
    ]}]}
    assert repair_continuation_labels(design) == design
    missing = deepcopy(design)
    missing["scenes"][0]["lines"].pop()
    repaired = repair_continuation_labels(missing)
    assert repaired["scenes"][0]["lines"][1]["branchLabel"] == target
