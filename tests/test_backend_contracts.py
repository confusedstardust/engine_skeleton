from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path

from webgal_backend import game_design
from webgal_backend.artifacts import NODE_ARTIFACTS, artifact_key_for_path, is_editable_artifact
from webgal_backend.job_options import GenerationOptions, normalize_generation_options, validate_generation_options
from webgal_backend.app import _contains_hidden_path, _public_app_path
from webgal_backend.narrative_structure import narrative_structure_issues, repair_narrative_structure_if_needed
from webgal_backend.pipeline import PipelineError, WebGALPipeline
from webgal_backend.prompts import game_design_completion_prompt
from webgal_backend.raw_correction import correct_generated_raw_file, correct_inline_dialogue_direction
from webgal_backend.scene_plan import build_scene_plan, expected_ending_types, expected_scene_files, expected_source_nodes
from webgal_backend.scene_validation import _repair_scene_lines
from webgal_backend.scene_validation import _parse_choose_options, _scene_targets
from webgal_backend.storage import JobStore
from webgal_backend.tts_pipeline import build_tts_manifest
from webgal_backend.validators import validate_schema


VALID_OPTIONS = {
    "classroom_topic": "文学阅读",
    "grade": "高中语文",
    "difficulty": "中等",
    "teacher_goal": "理解人物关系",
    "student_goal": "能解释关键选择的后果",
    "duration": "20分钟",
    "narrative_mode": "角色扮演",
    "character_count": 3,
    "interactive_task_count": 6,
    "voice_enabled": False,
    "generate_assets": False,
}


def minimal_narrative_plan() -> dict:
    return {
        "title": "测试故事",
        "theme": "选择与后果",
        "emotion_tone": "克制",
        "conflict_structure": "人物在误解中做出选择",
        "story_progression": [
            {
                "id": "phase0",
                "name": "开端",
                "content": "建立目标和疑问。",
                "narrative_target": "让玩家理解当前处境。",
                "strtype": "main",
            }
        ],
        "story_arc": "从疑问到承担后果。",
        "characters": [
            {
                "id": "main_role",
                "name": "主角",
                "gender": "未知",
                "personality": "谨慎但会犹豫",
                "motivation": "想完成任务",
                "speech_style": "简短克制",
                "emotional_arc": "逐步理解责任",
                "relationships": [],
            }
        ],
        "touchable_points": ["犹豫"],
        "must_avoid": ["说教"],
        "endings": [{"ending_type": "true ending", "description": "承担后果。"}],
        "beat_structure": ["开端", "发展", "结局"],
        "narrative_structure": "flowchart TD\n  A[开端] --> B[结局]",
    }


class BackendContractTests(unittest.TestCase):
    def test_artifact_catalog_exposes_stable_labels_and_keys(self) -> None:
        self.assertEqual(NODE_ARTIFACTS[0].title, "\u6545\u4e8b\u5927\u7eb2")
        self.assertEqual(artifact_key_for_path("state/narrative_plan.json"), "narrative_plan")
        self.assertEqual(artifact_key_for_path("public/game/scene/start.txt"), "public_game_scene_start_txt")
        self.assertTrue(is_editable_artifact("state/game_design_completed.json"))
        self.assertTrue(is_editable_artifact("public/game/scene/start.txt"))
        self.assertFalse(is_editable_artifact("public/game/background/bg.png"))

    def test_public_app_path_keeps_optional_frontend_subpath(self) -> None:
        import webgal_backend.app as backend_app

        original = backend_app.frontend_url
        try:
            backend_app.frontend_url = "http://127.0.0.1:3001/narrativeos"
            self.assertEqual(_public_app_path("/play/job-1/assets/file.css"), "/narrativeos/play/job-1/assets/file.css")
            backend_app.frontend_url = "http://127.0.0.1:3001"
            self.assertEqual(_public_app_path("/play/job-1/assets/file.css"), "/play/job-1/assets/file.css")
        finally:
            backend_app.frontend_url = original

    def test_pipeline_phase_registry_keeps_aliases_available(self) -> None:
        pipeline = WebGALPipeline()
        phases = pipeline.phase_names()
        self.assertIn("sound_effects", phases)
        self.assertIn("sound", phases)
        self.assertIn("tts_generation", phases)
        self.assertIn("tts", phases)

    def test_generation_options_require_frontend_contract(self) -> None:
        validate_generation_options(dict(VALID_OPTIONS))
        with self.assertRaises(ValueError) as missing:
            validate_generation_options({"generate_assets": False})
        self.assertIn("missing required options", str(missing.exception))

    def test_voice_preset_required_when_voice_enabled(self) -> None:
        options = dict(VALID_OPTIONS)
        options["voice_enabled"] = True
        with self.assertRaises(ValueError) as invalid:
            validate_generation_options(options)
        self.assertIn("voice_preset is required", str(invalid.exception))

    def test_generation_options_normalize_and_preserve_extras(self) -> None:
        options = dict(VALID_OPTIONS)
        options["classroom_topic"] = "  文学阅读  "
        options["output_packages"] = ["学生端游戏"]
        options["custom_flag"] = "kept"
        normalized = normalize_generation_options(options)
        self.assertEqual(normalized["classroom_topic"], "文学阅读")
        self.assertEqual(normalized["output_packages"], ["学生端游戏"])
        self.assertEqual(normalized["custom_flag"], "kept")
        self.assertIsInstance(validate_generation_options(options), GenerationOptions)

    def test_generation_options_reject_string_booleans(self) -> None:
        options = dict(VALID_OPTIONS)
        options["voice_enabled"] = "false"
        with self.assertRaises(ValueError) as invalid:
            validate_generation_options(options)
        self.assertIn("voice_enabled must be a boolean", str(invalid.exception))

    def test_scene_headers_split_new_scene_and_ending_format(self) -> None:
        text = "Scene:start.txt\n一句话。\n\nScene:branch_1.txt\n分支。\n\nEnding:ending_1.txt\n结局。"
        with tempfile.TemporaryDirectory() as tmp:
            pipeline = WebGALPipeline()
            files = pipeline._split_game_design_completed_to_scene_files(Path(tmp), text)
            self.assertEqual(
                files,
                [
                    "public/game/scene/start.txt",
                    "public/game/scene/branch_1.txt",
                    "public/game/scene/ending_1.txt",
                ],
            )

    def test_scene_plan_maps_narrative_nodes_to_files(self) -> None:
        plan = build_scene_plan(minimal_narrative_plan())
        self.assertEqual(plan["required_scene_count"], 2)
        self.assertEqual(expected_scene_files(plan), ["start.txt", "ending_1.txt"])
        self.assertEqual(expected_source_nodes(plan), ["phase0"])
        self.assertEqual(expected_ending_types(plan), ["true ending"])

    def test_game_design_coverage_requires_all_scene_files(self) -> None:
        pipeline = WebGALPipeline()
        scene_plan = build_scene_plan(minimal_narrative_plan())
        text = "\n".join(
            [
                "Scene:start.txt",
                "一句话。",
                "",
                "Ending:ending_1.txt",
                "结局。",
            ]
        )
        pipeline._validate_game_design_coverage(text, scene_plan, "game_design.json")
        with self.assertRaises(PipelineError):
            pipeline._validate_game_design_coverage(
                "Scene:start.txt\n一句话。",
                scene_plan,
                "game_design.json",
            )
        with self.assertRaises(PipelineError):
            pipeline._validate_game_design_coverage(
                "Scene:renamed.txt\n一句话。\nEnding:ending_1.txt\n结局。",
                scene_plan,
                "game_design.json",
            )

    def test_game_design_choices_are_inserted_without_internal_metadata(self) -> None:
        text = "\n".join(
            [
                "Scene:start.txt",
                "; source_node: phase0",
                "intro:开场。",
                "",
                "Ending:ending_1.txt",
                "; ending_type: true ending",
                "intro:结局。",
            ]
        )
        completed = game_design.apply_choices_to_text(
            text,
            {
                "choices_group": [
                    {
                        "id": "start_choice_1",
                        "scene_file": "start.txt",
                        "insert_index": 1,
                        "content": "他停在门前，终于做出了选择。",
                        "choices": ["走向结局", "暂时留下"],
                    }
                ]
            },
        )
        self.assertIn(">旁白:他停在门前，终于做出了选择。;", completed)
        self.assertIn("choose:走向结局:start_choice_1_1|暂时留下:start_choice_1_2;", completed)
        self.assertIn(":start_choice_1_1", completed)
        self.assertIn(">旁白:走向结局;", completed)
        self.assertNotIn("source_node", completed)
        self.assertNotIn("ending_type", completed)

    def test_game_design_choices_normalize_to_simple_choices_group_contract(self) -> None:
        pipeline = WebGALPipeline()
        plan = minimal_narrative_plan()
        normalized = pipeline._normalize_game_design_choices(
            {
                "choices_group": [
                    {
                        "id": "start_choice_1",
                        "scene_file": "start.txt",
                        "insert_index": 99,
                        "content": "他停在门前。",
                        "choices": ["走向结局", "暂时留下", "回头询问", "多余选项"],
                    }
                ]
            },
            build_scene_plan(plan),
            {"scene": [{"scene_file": "start.txt", "content": "intro:开场。"}], "endings": []},
        )

        self.assertEqual(list(normalized), ["choices_group"])
        self.assertNotIn("choice_groups", normalized)
        self.assertEqual(normalized["choices_group"][0]["insert_index"], 1)
        self.assertEqual(normalized["choices_group"][0]["choices"], ["走向结局", "暂时留下", "回头询问"])
        self.assertNotIn("branches", normalized["choices_group"][0])

    def test_narrative_structure_edges_become_connectable_pairs(self) -> None:
        pipeline = WebGALPipeline()
        plan = minimal_narrative_plan()
        plan["story_progression"].append(
            {
                "id": "phase1",
                "name": "second",
                "content": "next scene",
                "narrative_target": "continue",
                "strtype": "main",
            }
        )
        plan["narrative_structure"] = "flowchart TD\n  phase0 -->|accept| phase1\n  phase1 --> true_ending"
        scene_plan = build_scene_plan(plan)
        outline = game_design.extract_outline(
            {
                "scenes": [
                    {"scene_file": "start.txt", "lines": [{"kind": "narration", "text": "opening"}]},
                    {"scene_file": "phase1.txt", "lines": [{"kind": "narration", "text": "next"}]},
                    {"scene_file": "ending_1.txt", "marker": "Ending", "lines": [{"kind": "narration", "text": "ending"}]},
                ]
            },
            plan,
            scene_plan,
        )
        pairs = outline["connectable_pairs"]
        self.assertTrue(any(pair["source_scene_file"] == "start.txt" and pair["target_scene_file"] == "phase1.txt" for pair in pairs))
        self.assertTrue(any(pair["source_scene_file"] == "phase1.txt" and pair["target_scene_file"] == "ending_1.txt" for pair in pairs))

    def test_narrative_structure_reports_unknown_nodes(self) -> None:
        plan = minimal_narrative_plan()
        plan["narrative_structure"] = "flowchart TD\n  phase0 --> missing_phase\n  missing_phase --> true_ending"
        issues = narrative_structure_issues(plan)
        self.assertEqual([issue["node"] for issue in issues], ["missing_phase"])

    def test_narrative_structure_repair_only_updates_structure(self) -> None:
        class FakeLLM:
            prompt = ""

            def call_text(self, _trace_name: str, _system_prompt: str, user_prompt: str, thinking: str | None = None) -> str:
                self.prompt = user_prompt
                return json.dumps({"narrative_structure": "flowchart TD\n  phase0 --> true_ending[true ending]"})

            def parse_json_text(self, text: str, _trace_name: str) -> dict:
                return json.loads(text)

        fake = FakeLLM()
        plan = minimal_narrative_plan()
        plan["narrative_structure"] = "flowchart TD\n  phase0 --> missing_phase"
        with tempfile.TemporaryDirectory() as tmp:
            repaired = repair_narrative_structure_if_needed(
                narrative_plan=plan,
                job_dir=Path(tmp),
                llm_factory=lambda **_kwargs: fake,
            )
        self.assertEqual(repaired["narrative_structure"], "flowchart TD\n  phase0 --> true_ending[true ending]")
        self.assertEqual(repaired["story_progression"], plan["story_progression"])
        self.assertIn("missing_phase", fake.prompt)

    def test_game_design_choices_can_target_scene_files(self) -> None:
        pipeline = WebGALPipeline()
        plan = minimal_narrative_plan()
        plan["story_progression"].append(
            {
                "id": "phase1",
                "name": "second",
                "content": "next scene",
                "narrative_target": "continue",
                "strtype": "main",
            }
        )
        scene_plan = build_scene_plan(plan)
        outline = {
            "scene": [
                {"scene_file": "start.txt", "content": "intro:opening;"},
                {"scene_file": "phase1.txt", "content": "intro:next;"},
            ],
            "endings": [{"ending_file": "ending_1.txt", "content": "intro:ending;"}],
        }
        normalized = pipeline._normalize_game_design_choices(
            {
                "choices_group": [
                    {
                        "id": "start_choice_1",
                        "scene_file": "start.txt",
                        "insert_index": 1,
                        "content": "A choice appears.",
                        "choices": [{"text": "Take the hoe", "target_scene_file": "phase1.txt"}],
                    }
                ]
            },
            scene_plan,
            outline,
        )
        lines = game_design.choice_group_to_scene_lines(normalized["choices_group"][0])
        choice_line = next(line for line in lines if line["kind"] == "choice")
        self.assertEqual(choice_line["choices"][0]["target"], "phase1.txt")
        self.assertFalse(any(line.get("kind") == "branch" for line in lines))

    def test_game_design_json_reader_no_longer_accepts_legacy_text_artifact(self) -> None:
        pipeline = WebGALPipeline()
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)
            state_dir = job_dir / "state"
            state_dir.mkdir(parents=True, exist_ok=True)
            (state_dir / "game_design.txt").write_text("Scene:start.txt\nintro:test;\n", encoding="utf-8")
            with self.assertRaises(PipelineError) as error:
                pipeline._read_game_design_json(job_dir)
        self.assertIn("game_design.json is required", str(error.exception))

    def test_game_design_completion_prompt_allows_literal_choice_object_example(self) -> None:
        plan = minimal_narrative_plan()
        prompt = game_design_completion_prompt(
            plan,
            {
                "scene": [{"scene_file": "start.txt", "scene_name": "phase0", "content": "intro:opening;", "strtype": "main"}],
                "endings": [{"ending_file": "ending_1.txt", "ending_type": "true ending", "content": "intro:ending;"}],
                "connectable_pairs": [
                    {
                        "source_scene_file": "start.txt",
                        "target_scene_file": "ending_1.txt",
                        "source_content": "intro:opening;",
                        "target_content": "intro:ending;",
                    }
                ],
                "narrative_structure": "phase0 --> true_ending",
            },
            VALID_OPTIONS,
        )
        self.assertIn('"text": "..."', prompt)
        self.assertIn('"target_scene_file": "..."', prompt)

    def test_sound_effect_commands_use_vocal_directory(self) -> None:
        pipeline = WebGALPipeline()
        command = pipeline._sound_effect_command(
            {"asset": "door-open.mp3", "category": "event", "operation": "start", "playback": "once"},
            {},
        )
        self.assertEqual(command, "playEffect:./game/vocal/door-open.mp3 -volume=75 -next;")

    def test_choose_parser_respects_escaped_separators(self) -> None:
        line = r"choose:说出\:留下来:branch_1.txt|沉默\|点头:branch_2.txt;"
        self.assertEqual(
            _parse_choose_options(line),
            [("说出:留下来", "branch_1.txt"), ("沉默|点头", "branch_2.txt")],
        )
        self.assertEqual(_scene_targets(line), ["branch_1.txt", "branch_2.txt"])

    def test_inline_dialogue_directions_are_removed(self) -> None:
        line = "陶渊明：（踱步，语气渐坚）方才我还犹豫。"
        self.assertEqual(correct_inline_dialogue_direction(line), "陶渊明：方才我还犹豫。")
        corrected = correct_generated_raw_file(line, minimal_narrative_plan())
        self.assertEqual(corrected.strip(), "陶渊明：方才我还犹豫。")

    def test_scene_validation_repairs_inline_dialogue_directions(self) -> None:
        repaired, _issues, fixes = _repair_scene_lines(
            ["陶渊明：（踱步，语气渐坚）方才我还犹豫。"],
            "public/game/scene/start.txt",
            {},
            {},
        )
        self.assertIn("陶渊明：方才我还犹豫。", repaired)
        self.assertTrue(any(fix.code == "remove_inline_dialogue_direction" for fix in fixes))

    def test_ending_scene_missing_end_is_repaired(self) -> None:
        repaired, _issues, fixes = _repair_scene_lines(
            [":Final narration;"],
            "public/game/scene/ending_1.txt",
            {},
            {},
        )
        self.assertEqual(repaired[-1], "end;")
        self.assertEqual(repaired[-4:-1], ["changeFigure:none;", "changeFigure:none -left;", "changeFigure:none -right;"])
        self.assertTrue(any(fix.code == "missing_ending_end" for fix in fixes))

    def test_narrative_schema_rejects_incomplete_ending(self) -> None:
        plan = minimal_narrative_plan()
        validate_schema("narrative_plan.schema.json", plan)
        broken = minimal_narrative_plan()
        broken["endings"] = [{"ending_type": "true ending"}]
        with self.assertRaises(Exception):
            validate_schema("narrative_plan.schema.json", broken)

    def test_narrative_normalizer_removes_unexpected_root_fields_before_schema_validation(self) -> None:
        plan = minimal_narrative_plan()
        plan["narrative_target"] = "这个字段不应出现在根对象。"
        pipeline = WebGALPipeline()
        normalized = pipeline._normalize_narrative_design(plan)
        self.assertNotIn("narrative_target", normalized)
        validate_schema("narrative_plan.schema.json", normalized)

    def test_hidden_paths_are_blocked_from_public_routes(self) -> None:
        self.assertTrue(_contains_hidden_path(".env"))
        self.assertTrue(_contains_hidden_path("public/game/.env"))
        self.assertFalse(_contains_hidden_path("background/bg_school.webp"))

    def test_tts_manifest_can_select_key_lines_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)
            (job_dir / "state").mkdir()
            plan = minimal_narrative_plan()
            plan["characters"] = [
                {
                    "id": "hero",
                    "name": "Hero",
                    "gender": "male",
                    "personality": "calm",
                    "motivation": "choose freely",
                    "speech_style": "direct",
                    "emotional_arc": "hesitation to resolve",
                    "relationships": [],
                }
            ]
            (job_dir / "state" / "narrative_plan.json").write_text(
                json.dumps(plan, ensure_ascii=False),
                encoding="utf-8",
            )
            (job_dir / "state" / "game_design_webgal.txt").write_text(
                "\n".join(
                    [
                        "Scene:start.txt",
                        "Hero: First line.",
                        "Hero: Why can I not return?",
                        "Hero: A plain explanation.",
                        "Hero: I have made my decision.",
                        "",
                        "Scene:phase1.txt",
                        "Hero: Another first line.",
                        "Hero: But my heart still asks!",
                        "Hero: Another final line.",
                    ]
                ),
                encoding="utf-8",
            )

            manifest = build_tts_manifest(
                job_dir,
                character_voices={"Hero": ["Ethan", ""]},
                selection_options={"tts_scope": "key_lines", "tts_max_lines_per_scene": 2, "tts_max_total_lines": 3},
            )
            pending = [item for item in manifest["items"] if item["status"] == "pending"]
            skipped = [item for item in manifest["items"] if item["status"] == "skipped_non_key"]
            self.assertEqual(len(pending), 3)
            self.assertGreater(len(skipped), 0)
            self.assertTrue(all(item["is_key_line"] for item in pending))

            full_manifest = build_tts_manifest(
                job_dir,
                character_voices={"Hero": ["Ethan", ""]},
                selection_options={"tts_scope": "all"},
            )
            self.assertEqual(len([item for item in full_manifest["items"] if item["status"] == "pending"]), 7)

    def test_job_store_rejects_non_uuid_job_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp))
            with self.assertRaises(FileNotFoundError):
                store.job_dir("..")
            with self.assertRaises(FileNotFoundError):
                store.job_dir("not-a-job-id")


if __name__ == "__main__":
    unittest.main()
