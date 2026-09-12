from __future__ import annotations

from pathlib import Path

import pytest

from webgal_backend.pipeline import WebGALPipeline
from webgal_backend.script_compiler import ScriptCompileError, compile_webgal_script
from webgal_backend.storage import JobStore, read_json, write_json
from webgal_backend.validators import validate_schema


def _narrative_plan() -> dict:
    return {
        "title": "Test",
        "characters": [
            {"id": "hero", "name": "主角"},
            {"id": "friend", "name": "朋友"},
        ],
    }


def _completed_design() -> dict:
    return {
        "version": 1,
        "scenes": [
            {
                "marker": "Scene",
                "scene_file": "start.txt",
                "lines": [
                    {"id": "start-0", "kind": "dialogue", "speaker": "主角抬起头", "text": "先说；一句。"},
                    {
                        "id": "start-choice",
                        "kind": "choice",
                        "choices": [{"text": "继续:前进", "target_scene_file": "ending_1.txt"}],
                    },
                    {"id": "start-2", "kind": "dialogue", "speaker": "朋友", "text": "选项前的尾句。"},
                ],
            },
            {
                "marker": "Ending",
                "scene_file": "ending_1.txt",
                "lines": [{"id": "ending-0", "kind": "narration", "text": "结束。", "rawPrefix": "intro"}],
            },
        ],
    }


def _manifest() -> dict:
    return {
        "base_dir": "ignored-by-compiler",
        "model": "test",
        "images": [
            {
                "filename": "figure_hero",
                "subdir": "figure",
                "size": "1440x2560",
                "prompt": "x" * 20,
                "available_scene": "",
                "usage": "figure",
                "character_id": "hero",
                "insert_before_line_id": "",
            },
            {
                "filename": "figure_friend",
                "subdir": "figure",
                "size": "1440x2560",
                "prompt": "x" * 20,
                "available_scene": "",
            },
            {
                "filename": "bg_room",
                "subdir": "background",
                "size": "2560x1440",
                "prompt": "x" * 20,
                "available_scene": "start.txt",
                "usage": "scene_background",
                "character_id": "",
                "insert_before_line_id": "",
            },
            {
                "filename": "cg_reveal",
                "subdir": "background",
                "size": "2560x1440",
                "prompt": "x" * 20,
                "available_scene": "start.txt",
                "usage": "event_cg",
                "character_id": "",
                "insert_before_line_id": "start-2",
            },
        ],
    }


def test_compiler_places_reviewed_assets_and_moves_cross_scene_choice_to_end() -> None:
    result = compile_webgal_script(_completed_design(), _narrative_plan(), _manifest())
    start = result.script.split("\n\nEnding:ending_1.txt", 1)[0]

    assert "changeBg:bg_room.webp -next;" in start
    assert "changeFigure:figure_hero.webp -left -next;\n主角抬起头:先说；一句。;" in start
    assert "changeBg:cg_reveal.webp -next;\nchangeFigure:figure_friend.webp -right -next;" in start
    assert start.rstrip().endswith("choose:继续：前进:ending_1.txt;")
    assert result.script.rstrip().endswith("end;")
    assert result.plan["compiler"] == "deterministic-webgal-v1"
    assert result.plan["scenes"][0]["terminal_choice_moved_to_end"] is True
    assert result.plan["warnings"] == []


def test_compiler_reports_unanchored_additional_background() -> None:
    manifest = _manifest()
    manifest["images"][-1]["insert_before_line_id"] = "missing-line"

    result = compile_webgal_script(_completed_design(), _narrative_plan(), manifest)

    assert "changeBg:cg_reveal.webp" not in result.script
    assert "ignored additional background cg_reveal.webp" in result.plan["warnings"][0]


def test_compiler_rejects_unsafe_choice_target() -> None:
    design = _completed_design()
    design["scenes"][0]["lines"][1]["choices"][0]["target_scene_file"] = "../ending.txt"

    with pytest.raises(ScriptCompileError, match="invalid choice target"):
        compile_webgal_script(design, _narrative_plan(), _manifest())


def test_compiler_rejects_empty_scene_collection() -> None:
    with pytest.raises(ScriptCompileError, match="at least one scene"):
        compile_webgal_script({"version": 1, "scenes": []}, _narrative_plan(), _manifest())


def test_compiler_rejects_unsafe_scene_filename() -> None:
    design = _completed_design()
    design["scenes"][0]["scene_file"] = "../start.txt"

    with pytest.raises(ScriptCompileError, match="invalid scene filename"):
        compile_webgal_script(design, _narrative_plan(), _manifest())


def test_compiler_merges_multiple_cross_scene_choice_groups_without_losing_wording() -> None:
    design = _completed_design()
    design["scenes"][0]["lines"].append(
        {
            "id": "start-choice-2",
            "kind": "choice",
            "choices": [
                {"text": "换一种说法", "target_scene_file": "ending_1.txt"},
                {"text": "走向另一结局", "target_scene_file": "ending_2.txt"},
            ],
        }
    )
    design["scenes"].append(
        {
            "marker": "Ending",
            "scene_file": "ending_2.txt",
            "lines": [{"id": "ending-2-0", "kind": "narration", "text": "另一个结束。"}],
        }
    )

    result = compile_webgal_script(design, _narrative_plan(), _manifest())
    start = result.script.split("\n\nEnding:ending_1.txt", 1)[0]

    assert start.count("choose:") == 1
    assert "choose:继续：前进:ending_1.txt|换一种说法:ending_1.txt|走向另一结局:ending_2.txt;" in start
    assert result.plan["scenes"][0]["terminal_choice_groups_merged"] == 2
    assert result.plan["scenes"][0]["terminal_choice_targets"] == ["ending_1.txt", "ending_2.txt"]
    assert "into 3 options across 2 destinations" in result.plan["warnings"][0]


@pytest.mark.parametrize(
    ("speaker_count", "expected_positions"),
    [
        (1, ["center"]),
        (2, ["left", "right"]),
        (3, ["center", "left", "right"]),
    ],
)
def test_compiler_assigns_stable_figure_slots(
    speaker_count: int, expected_positions: list[str]
) -> None:
    character_ids = ["hero", "friend", "mentor"]
    character_names = ["主角", "朋友", "导师"]
    narrative_plan = {
        "title": "Test",
        "characters": [
            {"id": character_id, "name": name}
            for character_id, name in zip(character_ids, character_names, strict=True)
        ],
    }
    design = {
        "version": 1,
        "scenes": [
            {
                "marker": "Scene",
                "scene_file": "start.txt",
                "lines": [
                    {"id": f"line-{index}", "kind": "dialogue", "speaker": character_names[index], "text": "台词"}
                    for index in range(speaker_count)
                ],
            }
        ],
    }
    manifest = {
        "images": [
            {
                "filename": f"figure_{character_id}",
                "subdir": "figure",
                "character_id": character_id,
            }
            for character_id in character_ids
        ]
    }

    result = compile_webgal_script(design, narrative_plan, manifest)

    assert [slot["position"] for slot in result.plan["scenes"][0]["figure_slots"]] == expected_positions
    assert len([line for line in result.script.splitlines() if line.startswith("changeFigure:figure_")]) == speaker_count


def test_asset_manifest_schema_accepts_explicit_compiler_bindings() -> None:
    manifest = _manifest()
    manifest["base_dir"] = "C:/tmp/game"

    validate_schema("asset_manifest.schema.json", manifest)


def test_pipeline_uses_deterministic_compiler_without_llm(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs")
    job = store.create("source")
    job_dir = store.job_dir(job["id"])
    write_json(job_dir / "state" / "narrative_plan.json", _narrative_plan())
    write_json(job_dir / "state" / "game_design_completed.json", _completed_design())
    write_json(job_dir / "assets_manifest.json", _manifest())
    pipeline = WebGALPipeline(store=store, llm_factory=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("LLM called")))

    pipeline.run_script_rewrite(job)

    assert (job_dir / "state" / "game_design_webgal.txt").exists()
    assert read_json(job_dir / "state" / "script_compile_plan.json")["compiler"] == "deterministic-webgal-v1"
    assert store.get(job["id"])["artifacts"]["script_compile_plan"] == "state/script_compile_plan.json"
    scene_files = pipeline._split_game_design_completed_to_scene_files(  # noqa: SLF001
        job_dir,
        (job_dir / "state" / "game_design_webgal.txt").read_text(encoding="utf-8"),
    )
    assert scene_files == ["public/game/scene/start.txt", "public/game/scene/ending_1.txt"]
    ending_text = (job_dir / "public" / "game" / "scene" / "ending_1.txt").read_text(encoding="utf-8")
    assert ending_text.rstrip().endswith("end;")
