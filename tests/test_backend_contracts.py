from __future__ import annotations

import tempfile
import threading
import time
import unittest
import json
import os
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from webgal_backend import game_design
from webgal_backend.artifacts import NODE_ARTIFACTS, artifact_key_for_path, is_editable_artifact
from webgal_backend.job_options import GenerationOptions, normalize_generation_options, validate_generation_options
from webgal_backend.app import _contains_hidden_path, _enqueue_job_task, _execute_queued_task, _public_app_path
from webgal_backend.config import settings
from webgal_backend.game_project import EdgeKind, compile_game_project, completed_from_game_project, game_project_from_completed
from webgal_backend.narrative_structure import narrative_structure_issues, repair_narrative_structure_if_needed
from webgal_backend.pipeline import PipelineError, WebGALPipeline
from webgal_backend.prompts import game_design_completion_prompt
from webgal_backend.publisher import (
    PublishError,
    activate_game_revision,
    current_publication,
    list_game_revisions,
    publish_game_revision,
    published_game_root,
)
from webgal_backend.raw_correction import correct_generated_raw_file, correct_inline_dialogue_direction
from webgal_backend.scene_plan import build_scene_plan, expected_ending_types, expected_scene_files, expected_source_nodes
from webgal_backend.scene_validation import _repair_scene_lines, _validate_scene_graph, repair_scenes, validate_scenes
from webgal_backend.scene_validation import _parse_choose_options, _scene_targets
from webgal_backend.script_enrichment import normalize_asset_operations
from webgal_backend.storage import (
    ConcurrentJobUpdateError,
    JobBusyError,
    JobStore,
    read_json,
    write_json,
    write_text_atomic,
)
from webgal_backend.task_queue import DurableTaskQueue, DurableTaskWorker, QueueBusyError, QueuedTask
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

    def test_job_apis_are_scoped_by_invite_code(self) -> None:
        import webgal_backend.app as backend_app

        original_store = backend_app.store
        original_file = os.environ.get("WEBGAL_INVITE_CODES_FILE")
        original_codes = os.environ.get("WEBGAL_INVITE_CODES")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                invite_file = tmp_path / "invite-codes.txt"
                invite_file.write_text("alpha\nbeta\n内测码一\n", encoding="utf-8")
                os.environ["WEBGAL_INVITE_CODES_FILE"] = str(invite_file)
                os.environ.pop("WEBGAL_INVITE_CODES", None)
                backend_app.store = JobStore(tmp_path / "jobs")
                client = TestClient(backend_app.app)

                payload = {"source_material": "lesson", "options": VALID_OPTIONS}
                alpha_created = client.post("/jobs", json=payload, headers={"X-WebGAL-Invite-Code": "alpha"})
                beta_created = client.post("/jobs", json=payload, headers={"X-WebGAL-Invite-Code": "beta"})

                self.assertEqual(alpha_created.status_code, 200)
                self.assertEqual(beta_created.status_code, 200)
                alpha_id = alpha_created.json()["id"]
                beta_id = beta_created.json()["id"]

                alpha_jobs = client.get("/jobs", headers={"X-WebGAL-Invite-Code": "alpha"})
                self.assertEqual(alpha_jobs.status_code, 200)
                self.assertEqual([job["id"] for job in alpha_jobs.json()["jobs"]], [alpha_id])

                game_dir = backend_app.store.job_dir(alpha_id) / "public" / "game"
                (game_dir / "config.txt").write_text("Game_name:Demo;\n", encoding="utf-8")
                start = game_dir / "scene" / "start.txt"
                start.write_text("intro:First;\n", encoding="utf-8")
                first_publication = publish_game_revision(backend_app.store.job_dir(alpha_id), source_revision=1)
                start.write_text("intro:Second;\n", encoding="utf-8")
                publish_game_revision(backend_app.store.job_dir(alpha_id), source_revision=2)
                publication_list = client.get(
                    f"/jobs/{alpha_id}/publication", headers={"X-WebGAL-Invite-Code": "alpha"}
                )
                self.assertEqual(publication_list.status_code, 200)
                self.assertEqual(len(publication_list.json()["revisions"]), 2)
                restored = client.post(
                    f"/jobs/{alpha_id}/publication/{first_publication['revision_id']}/activate",
                    headers={"X-WebGAL-Invite-Code": "alpha"},
                )
                self.assertEqual(restored.status_code, 200)
                self.assertEqual(restored.json()["publication"]["revision_id"], first_publication["revision_id"])

                self.assertEqual(client.get(f"/jobs/{alpha_id}", headers={"X-WebGAL-Invite-Code": "alpha"}).status_code, 200)
                self.assertEqual(client.get(f"/jobs/{beta_id}", headers={"X-WebGAL-Invite-Code": "alpha"}).status_code, 404)
                self.assertEqual(
                    client.post("/jobs", json=payload, headers={"X-WebGAL-Invite-Code": "%E5%86%85%E6%B5%8B%E7%A0%81%E4%B8%80"}).status_code,
                    200,
                )
                self.assertEqual(client.get("/jobs").status_code, 401)
                self.assertEqual(client.post("/jobs", json=payload, headers={"X-WebGAL-Invite-Code": "missing"}).status_code, 403)
        finally:
            backend_app.store = original_store
            if original_file is None:
                os.environ.pop("WEBGAL_INVITE_CODES_FILE", None)
            else:
                os.environ["WEBGAL_INVITE_CODES_FILE"] = original_file
            if original_codes is None:
                os.environ.pop("WEBGAL_INVITE_CODES", None)
            else:
                os.environ["WEBGAL_INVITE_CODES"] = original_codes

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
            stale = Path(tmp) / "public" / "game" / "scene" / "stale_branch.txt"
            stale.parent.mkdir(parents=True)
            stale.write_text("old branch", encoding="utf-8")
            files = pipeline._split_game_design_completed_to_scene_files(Path(tmp), text)
            self.assertEqual(
                files,
                [
                    "public/game/scene/start.txt",
                    "public/game/scene/branch_1.txt",
                    "public/game/scene/ending_1.txt",
                ],
            )
            self.assertFalse(stale.exists())

    def test_final_scene_graph_validation_rejects_orphan_endings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)
            scene_dir = job_dir / "public" / "game" / "scene"
            scene_dir.mkdir(parents=True)
            (scene_dir / "start.txt").write_text("changeScene:final.txt;\n", encoding="utf-8")
            (scene_dir / "final.txt").write_text("intro:No ending choice;\n", encoding="utf-8")
            (scene_dir / "ending_1.txt").write_text("end;\n", encoding="utf-8")
            issues = _validate_scene_graph(job_dir, sorted(scene_dir.glob("*.txt")))
            codes = {(issue.code, issue.file) for issue in issues}
            self.assertIn(("dead_end_scene", "public/game/scene/final.txt"), codes)
            self.assertIn(("orphan_ending", "public/game/scene/ending_1.txt"), codes)

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

    def test_game_design_coverage_normalizer_collapses_duplicate_scene_sections(self) -> None:
        pipeline = WebGALPipeline()
        scene_plan = build_scene_plan(minimal_narrative_plan())
        duplicated = "\n\n".join(
            [
                "Scene:start.txt\n第一版开场。",
                "Ending:ending_1.txt\n第一版结局。",
                "Scene:start.txt\n第二版开场。",
                "Ending:ending_1.txt\n第二版结局。",
            ]
        )

        normalized = pipeline._normalize_game_design_coverage_text(duplicated, scene_plan, "game_design.json")

        self.assertEqual(
            normalized,
            "\n\n".join(
                [
                    "Scene:start.txt\n第一版开场。",
                    "Ending:ending_1.txt\n第一版结局。",
                ]
            ),
        )

    def test_game_design_draft_retry_uses_previous_output_and_error_only(self) -> None:
        class FakeLLM:
            def __init__(self) -> None:
                self.prompts: list[str] = []
                self.responses = [
                    "Scene:start.txt\nintro:opening;",
                    "Scene:start.txt\nintro:opening;\n\nEnding:ending_1.txt\nintro:ending;",
                ]

            def call_text(self, _trace_name: str, _system_prompt: str, user_prompt: str, thinking: str | None = None) -> str:
                self.prompts.append(user_prompt)
                return self.responses[len(self.prompts) - 1]

        fake = FakeLLM()
        original_retry_count = settings.max_text_retries
        try:
            object.__setattr__(settings, "max_text_retries", 1)
            with tempfile.TemporaryDirectory() as tmp:
                store = JobStore(Path(tmp))
                job = store.create("SOURCE_MATERIAL_SENTINEL", dict(VALID_OPTIONS))
                job_dir = store.job_dir(job["id"])
                write_json(job_dir / "state" / "narrative_plan.json", minimal_narrative_plan())

                pipeline = WebGALPipeline(store=store, llm_factory=lambda **_kwargs: fake)
                pipeline.run_game_design_draft(job)

                saved = read_json(job_dir / "state" / "game_design.json")
        finally:
            object.__setattr__(settings, "max_text_retries", original_retry_count)

        self.assertEqual(len(fake.prompts), 2)
        self.assertIn("missing_scene_files=['ending_1.txt']", fake.prompts[1])
        self.assertIn("Scene:start.txt\nintro:opening;", fake.prompts[1])
        self.assertNotIn("SOURCE_MATERIAL_SENTINEL", fake.prompts[1])
        self.assertEqual([scene["scene_file"] for scene in saved["scenes"]], ["start.txt", "ending_1.txt"])

    def test_structured_retry_uses_previous_output_and_error_only(self) -> None:
        class FakeLLM:
            def __init__(self, broken: dict, fixed: dict) -> None:
                self.prompts: list[str] = []
                self.responses = [
                    json.dumps({"narrative_plan": broken}, ensure_ascii=False),
                    json.dumps({"narrative_plan": fixed}, ensure_ascii=False),
                ]

            def call_text(self, _trace_name: str, _system_prompt: str, user_prompt: str, thinking: str | None = None) -> str:
                self.prompts.append(user_prompt)
                return self.responses[len(self.prompts) - 1]

            def parse_json_text(self, text: str, _trace_name: str) -> dict:
                return json.loads(text)

        fixed = minimal_narrative_plan()
        broken = dict(fixed)
        broken.pop("title")
        fake = FakeLLM(broken, fixed)
        original_retry_count = settings.max_schema_retries
        try:
            object.__setattr__(settings, "max_schema_retries", 1)
            with tempfile.TemporaryDirectory() as tmp:
                pipeline = WebGALPipeline(llm_factory=lambda **_kwargs: fake)
                artifact = pipeline._call_with_validation(
                    job_dir=Path(tmp),
                    function_name="emit_narrative_plan",
                    artifact_key="narrative_plan",
                    schema_name="narrative_plan.schema.json",
                    user_prompt="STRUCTURED_SOURCE_SENTINEL",
                    semantic_validator=None,
                )
        finally:
            object.__setattr__(settings, "max_schema_retries", original_retry_count)

        self.assertEqual(artifact["title"], fixed["title"])
        self.assertEqual(len(fake.prompts), 2)
        self.assertIn('"theme"', fake.prompts[1])
        self.assertIn("title", fake.prompts[1])
        self.assertNotIn("STRUCTURED_SOURCE_SENTINEL", fake.prompts[1])

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

    def test_chinese_ending_ids_become_connectable_pairs(self) -> None:
        plan = minimal_narrative_plan()
        plan["endings"] = [
            {"ending_type": "真结局", "description": "守住本心。"},
            {"ending_type": "普通结局", "description": "留下遗憾。"},
        ]
        plan["narrative_structure"] = "flowchart TD\n  phase0 --> 真结局\n  phase0 --> 普通结局"
        scene_plan = build_scene_plan(plan)
        outline = game_design.extract_outline(
            {
                "scenes": [
                    {"scene_file": "start.txt", "lines": [{"kind": "narration", "text": "opening"}]},
                    {"scene_file": "ending_1.txt", "marker": "Ending", "lines": []},
                    {"scene_file": "ending_2.txt", "marker": "Ending", "lines": []},
                ]
            },
            plan,
            scene_plan,
        )

        self.assertEqual(
            {(pair["source_scene_file"], pair["target_scene_file"]) for pair in outline["connectable_pairs"]},
            {("start.txt", "ending_1.txt"), ("start.txt", "ending_2.txt")},
        )
        self.assertEqual(narrative_structure_issues(plan), [])

    def test_choice_normalization_fills_missing_final_ending_edges(self) -> None:
        plan = minimal_narrative_plan()
        plan["story_progression"].append(
            {
                "id": "phase1",
                "name": "final scene",
                "content": "closure",
                "narrative_target": "choose an ending",
                "strtype": "main",
            }
        )
        plan["endings"] = [
            {"ending_type": "真结局", "description": "守住本心。"},
            {"ending_type": "普通结局", "description": "留下遗憾。"},
        ]
        plan["narrative_structure"] = "flowchart TD\n  phase0 --> phase1\n  phase1 --> 真结局\n  phase1 --> 普通结局"
        scene_plan = build_scene_plan(plan)
        draft = {
            "version": 1,
            "scenes": [
                {"marker": "Scene", "scene_file": "start.txt", "lines": [{"kind": "narration", "text": "opening"}]},
                {"marker": "Scene", "scene_file": "phase1.txt", "lines": [{"kind": "narration", "text": "closure"}]},
                {"marker": "Ending", "scene_file": "ending_1.txt", "lines": [{"kind": "narration", "text": "true"}]},
                {"marker": "Ending", "scene_file": "ending_2.txt", "lines": [{"kind": "narration", "text": "normal"}]},
            ],
        }
        outline = game_design.extract_outline(draft, plan, scene_plan)
        normalized = game_design.normalize_choices(
            {
                "choices_group": [
                    {
                        "scene_file": "start.txt",
                        "insert_index": 1,
                        "choices": [{"text": "继续", "target_scene_file": "phase1.txt"}],
                    }
                ]
            },
            scene_plan,
            outline,
        )
        completed = game_design.apply_choices_to_json(draft, normalized)

        start_scene = next(scene for scene in completed["scenes"] if scene["scene_file"] == "start.txt")
        final_scene = next(scene for scene in completed["scenes"] if scene["scene_file"] == "phase1.txt")
        self.assertEqual([line["kind"] for line in start_scene["lines"] if line["kind"] in {"choice", "transition"}], ["transition"])
        self.assertEqual([line["kind"] for line in final_scene["lines"] if line["kind"] in {"choice", "transition"}], ["choice"])

        self.assertEqual(
            game_design.completed_control_flow_edges(completed),
            {
                ("start.txt", "phase1.txt"),
                ("phase1.txt", "ending_1.txt"),
                ("phase1.txt", "ending_2.txt"),
            },
        )
        self.assertEqual(game_design.completed_topology_errors(completed), [])

    def test_completed_topology_reports_dead_end_and_orphan_endings(self) -> None:
        completed = {
            "version": 1,
            "scenes": [
                {"marker": "Scene", "scene_file": "start.txt", "lines": []},
                {"marker": "Ending", "scene_file": "ending_1.txt", "lines": []},
                {"marker": "Ending", "scene_file": "ending_2.txt", "lines": []},
            ],
        }
        errors = game_design.completed_topology_errors(completed)
        self.assertIn("dead_end_scene:start.txt", errors)
        self.assertIn("orphan_ending:ending_1.txt", errors)
        self.assertIn("orphan_ending:ending_2.txt", errors)

    def test_completed_topology_rejects_duplicate_scene_files(self) -> None:
        completed = {
            "version": 1,
            "scenes": [
                {"marker": "Scene", "scene_file": "start.txt", "lines": [{"kind": "choice", "choices": [{"text": "End", "target_scene_file": "ending_1.txt"}]}]},
                {"marker": "Scene", "scene_file": "start.txt", "lines": []},
                {"marker": "Ending", "scene_file": "ending_1.txt", "lines": []},
            ],
        }
        self.assertIn("duplicate_scene_file:start.txt", game_design.completed_topology_errors(completed))

    def test_game_project_round_trip_keeps_typed_player_choices(self) -> None:
        completed = {
            "version": 1,
            "scenes": [
                {
                    "marker": "Scene",
                    "scene_file": "start.txt",
                    "lines": [
                        {"id": "opening", "kind": "narration", "text": "Choose."},
                        {
                            "id": "final-choice",
                            "kind": "choice",
                            "choices": [
                                {"text": "Stay", "target_scene_file": "ending_1.txt"},
                                {"text": "Leave", "target_scene_file": "ending_2.txt"},
                            ],
                        },
                    ],
                },
                {"marker": "Ending", "scene_file": "ending_1.txt", "lines": [{"kind": "narration", "text": "Stayed."}]},
                {"marker": "Ending", "scene_file": "ending_2.txt", "lines": [{"kind": "narration", "text": "Left."}]},
            ],
        }
        project = game_project_from_completed(completed)
        self.assertEqual({edge.kind for edge in project.edges}, {EdgeKind.PLAYER_CHOICE})
        self.assertEqual({edge.label for edge in project.edges}, {"Stay", "Leave"})
        compiled = compile_game_project(project)
        self.assertIn("choose:Stay:ending_1.txt|Leave:ending_2.txt;", compiled)
        round_tripped = completed_from_game_project(project)
        self.assertEqual(round_tripped["scenes"][0]["scene_id"], project.scenes[0].scene_id)

    def test_game_project_auto_transition_does_not_become_visible_choice(self) -> None:
        completed = {
            "version": 2,
            "scenes": [
                {
                    "marker": "Scene",
                    "scene_file": "start.txt",
                    "lines": [
                        {"kind": "narration", "text": "Continue."},
                        {"kind": "transition", "transition_kind": "AUTO_TRANSITION", "target_scene_file": "ending_1.txt"},
                    ],
                },
                {"marker": "Ending", "scene_file": "ending_1.txt", "lines": [{"kind": "narration", "text": "Done."}]},
            ],
        }
        project = game_project_from_completed(completed)
        self.assertEqual(project.edges[0].kind, EdgeKind.AUTO_TRANSITION)
        compiled = compile_game_project(project)
        self.assertIn("changeScene:ending_1.txt;", compiled)
        self.assertNotIn("choose:", compiled)

    def test_game_project_preserves_stable_ids_across_content_edits(self) -> None:
        completed = {
            "scenes": [
                {"marker": "Scene", "scene_file": "start.txt", "lines": [{"kind": "narration", "text": "Old"}, {"kind": "transition", "target_scene_file": "ending_1.txt"}]},
                {"marker": "Ending", "scene_file": "ending_1.txt", "lines": [{"kind": "narration", "text": "End"}]},
            ]
        }
        first = game_project_from_completed(completed)
        completed["scenes"][0]["lines"][0]["text"] = "New"
        second = game_project_from_completed(completed, previous=first)
        self.assertEqual(first.scenes[0].scene_id, second.scenes[0].scene_id)
        self.assertEqual(first.scenes[0].lines[0].line_id, second.scenes[0].lines[0].line_id)
        self.assertEqual(second.revision, first.revision + 1)

    def test_structured_asset_operations_cannot_change_story_graph(self) -> None:
        completed = {
            "scenes": [
                {
                    "marker": "Scene",
                    "scene_file": "start.txt",
                    "lines": [
                        {"id": "opening", "kind": "dialogue", "speaker": "Hero", "text": "Hello"},
                        {"kind": "choice", "choices": [{"text": "Finish", "target_scene_file": "ending_1.txt"}]},
                    ],
                },
                {"marker": "Ending", "scene_file": "ending_1.txt", "lines": [{"kind": "narration", "text": "Done"}]},
            ]
        }
        project = game_project_from_completed(completed)
        report = normalize_asset_operations(
            {
                "operations": [
                    {"scene_file": "start.txt", "position": "scene_start", "type": "background", "asset": "room.webp"},
                    {"scene_file": "start.txt", "line_id": "opening", "position": "before", "type": "figure", "asset": "hero.webp", "slot": "left"},
                    {"scene_file": "start.txt", "position": "scene_start", "type": "background", "asset": "../../evil.webp"},
                ]
            },
            project,
            background_assets=["room.webp"],
            figure_assets=["hero.webp"],
        )
        self.assertEqual(len(report["operations"]), 2)
        self.assertEqual(report["rejected"][0]["reason"], "unknown_background_asset")
        base = compile_game_project(project)
        enriched = compile_game_project(project, report["operations"])
        self.assertIn("changeBg:room.webp -next;", enriched)
        self.assertIn("changeFigure:hero.webp -left -next;", enriched)
        self.assertEqual(game_design.text_control_flow_edges(base), game_design.text_control_flow_edges(enriched))

    def test_script_rewrite_phase_uses_operations_not_full_script_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp))
            job = store.create("source", options=VALID_OPTIONS)
            job_dir = store.job_dir(job["id"])
            completed = {
                "scenes": [
                    {"marker": "Scene", "scene_file": "start.txt", "lines": [{"id": "opening", "kind": "dialogue", "speaker": "Hero", "text": "Hello"}, {"kind": "transition", "target_scene_file": "ending_1.txt"}]},
                    {"marker": "Ending", "scene_file": "ending_1.txt", "lines": [{"kind": "narration", "text": "Done"}]},
                ]
            }
            project = game_project_from_completed(completed)
            write_json(job_dir / "state" / "game_project.json", project.model_dump(mode="json"))
            write_json(job_dir / "state" / "game_design_completed.json", completed_from_game_project(project))
            write_json(job_dir / "assets_manifest.json", {"images": [{"filename": "room", "subdir": "background"}]})

            class FakeLLM:
                def call_text(self, *_args, **_kwargs):
                    return json.dumps({"operations": [{"scene_file": "start.txt", "position": "scene_start", "type": "background", "asset": "room.webp"}]})

                def parse_json_text(self, text, _name):
                    return json.loads(text)

            pipeline = WebGALPipeline(store, llm_factory=lambda **_kwargs: FakeLLM())
            pipeline.run_script_rewrite(job)
            script = (job_dir / "state" / "game_design_webgal.txt").read_text(encoding="utf-8")
            self.assertIn("changeBg:room.webp -next;", script)
            self.assertIn("changeScene:ending_1.txt;", script)
            self.assertNotIn("operations", script)
            operation_report = read_json(job_dir / "state" / "script_asset_operations.json")
            self.assertEqual(len(operation_report["operations"]), 1)

    def test_script_control_flow_edges_detect_rewritten_targets(self) -> None:
        original = "Scene:start.txt\nchoose:Stay:ending_1.txt;\n\nEnding:ending_1.txt\nend;"
        changed = "Scene:start.txt\nchoose:Stay:ending_2.txt;\n\nEnding:ending_1.txt\nend;"
        self.assertEqual(game_design.text_control_flow_edges(original), {("start.txt", "ending_1.txt")})
        self.assertEqual(game_design.text_control_flow_edges(changed), {("start.txt", "ending_2.txt")})

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

    def test_sound_effect_insertion_is_idempotent(self) -> None:
        pipeline = WebGALPipeline()
        plan = [{"anchor": "Hero: Open it;", "asset": "door-open.mp3", "category": "event", "operation": "start", "playback": "once"}]
        once, _ = pipeline._insert_sound_effects("Scene:start.txt\nHero: Open it;", plan)
        twice, report = pipeline._insert_sound_effects(once, plan)
        self.assertEqual(once, twice)
        self.assertEqual(report["skipped"][0]["reason"], "already_inserted")

    def test_vocal_arg_falls_back_to_dialogue_match_when_line_number_shifts(self) -> None:
        lines = [
            "playEffect:./game/vocal/door-open.mp3 -volume=75 -next;",
            "Hero: Why can I not return?;",
        ]
        vocal_map = {
            "by_line": {
                ("start.txt", 1): {
                    "filename": "start_001_hero.wav",
                    "speaker": "Hero",
                    "text": "Why can I not return?",
                }
            },
            "by_dialogue": {
                ("start.txt", "Hero", "Why can I not return?"): ["start_001_hero.wav"]
            },
        }

        repaired, _issues, fixes = _repair_scene_lines(
            lines,
            "public/game/scene/start.txt",
            {},
            vocal_map,
        )

        self.assertIn("Hero: Why can I not return? -start_001_hero.wav;", repaired)
        self.assertTrue(any(fix.code == "missing_vocal_arg" for fix in fixes))

    def test_existing_bare_vocal_filename_arg_is_not_duplicated(self) -> None:
        lines = ["Hero: Why can I not return? -start_001_hero.wav;"]
        vocal_map = {
            "by_line": {
                ("start.txt", 1): {
                    "filename": "start_001_hero.wav",
                    "speaker": "Hero",
                    "text": "Why can I not return?",
                }
            },
            "by_dialogue": {},
        }

        repaired, _issues, fixes = _repair_scene_lines(
            lines,
            "public/game/scene/start.txt",
            {},
            vocal_map,
        )

        self.assertEqual(repaired[0], lines[0])
        self.assertEqual(repaired[0].count("-start_001_hero.wav"), 1)
        self.assertFalse(any(fix.code == "missing_vocal_arg" for fix in fixes))

    def test_choose_parser_respects_escaped_separators(self) -> None:
        line = r"choose:说出\:留下来:branch_1.txt|沉默\|点头:branch_2.txt;"
        self.assertEqual(
            _parse_choose_options(line),
            [("说出:留下来", "branch_1.txt"), ("沉默|点头", "branch_2.txt")],
        )
        self.assertEqual(_scene_targets(line), ["branch_1.txt", "branch_2.txt"])

    def test_scene_validation_sanitizes_generated_comments_and_leaked_scene_filenames(self) -> None:
        repaired, _issues, fixes = _repair_scene_lines(
            [
                "// internal note for the writer",
                "Hero: Keep going // remove this note;",
                ": Follow phase1.txt clue;",
                "orphan_scene.txt",
                "Hero: Open https://example.com/path;",
                "choose:Go:phase1.txt|Stay:branch_2.txt;",
                "changeScene:phase1.txt;",
            ],
            "public/game/scene/start.txt",
            {},
            {},
        )

        self.assertNotIn("// internal note for the writer", repaired)
        self.assertIn("Hero: Keep going;", repaired)
        self.assertIn(": Follow clue;", repaired)
        self.assertNotIn("orphan_scene.txt", repaired)
        self.assertIn("Hero: Open https://example.com/path;", repaired)
        self.assertIn("choose:Go:phase1.txt|Stay:branch_2.txt;", repaired)
        self.assertIn("changeScene:phase1.txt;", repaired)
        self.assertTrue(any(fix.code == "remove_generated_comment" for fix in fixes))
        self.assertTrue(any(fix.code == "remove_leaked_scene_filename" for fix in fixes))

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

    def test_validation_is_read_only_and_repair_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)
            scene_dir = job_dir / "public" / "game" / "scene"
            scene_dir.mkdir(parents=True)
            (scene_dir / "start.txt").write_text("changeScene:ending_1.txt;\n", encoding="utf-8")
            ending_path = scene_dir / "ending_1.txt"
            ending_path.write_text("intro:Done;\n", encoding="utf-8")
            before = ending_path.read_text(encoding="utf-8")
            validation = validate_scenes(job_dir)
            self.assertEqual(ending_path.read_text(encoding="utf-8"), before)
            self.assertTrue(validation.suggested_fixes)
            repair = repair_scenes(job_dir)
            self.assertNotEqual(ending_path.read_text(encoding="utf-8"), before)
            self.assertTrue(repair.fixes)

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
            self.assertEqual(full_manifest["selection"]["scope"], "all")
            self.assertTrue(all(item["status"] == "pending" for item in full_manifest["items"]))

    def test_tts_filename_changes_when_dialogue_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)
            (job_dir / "state").mkdir()
            plan = minimal_narrative_plan()
            plan["characters"] = [{"id": "hero", "name": "Hero", "gender": "male"}]
            write_json(job_dir / "state" / "narrative_plan.json", plan)
            script_path = job_dir / "state" / "game_design_webgal.txt"
            script_path.write_text("Scene:start.txt\nHero: First version;\n", encoding="utf-8")
            first = build_tts_manifest(job_dir, character_voices={"Hero": ["Ethan", ""]}, selection_options={"tts_scope": "all"})
            script_path.write_text("Scene:start.txt\nHero: Revised version;\n", encoding="utf-8")
            second = build_tts_manifest(job_dir, character_voices={"Hero": ["Ethan", ""]}, selection_options={"tts_scope": "all"})
            self.assertNotEqual(first["items"][0]["filename"], second["items"][0]["filename"])

    def test_job_store_preserves_artifacts_across_stale_job_updates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp))
            created = store.create("source")
            other_store = JobStore(Path(tmp))
            first = store.get(created["id"])
            second = other_store.get(created["id"])
            write_json(store.artifact_path(created["id"], "state/a.json"), {"a": 1})
            store.record_artifact(first, "a", "state/a.json")
            other_store.transition(second, "RUNNING", "TEST")
            saved = store.get(created["id"])
            self.assertEqual(saved["artifacts"]["a"], "state/a.json")
            self.assertGreater(saved["state_version"], created["state_version"])

    def test_job_store_rejects_direct_stale_state_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp))
            created = store.create("source")
            first = store.get(created["id"])
            stale = store.get(created["id"])
            first["status"] = "FIRST_UPDATE"
            store.save(first)
            stale["status"] = "STALE_UPDATE"
            with self.assertRaises(ConcurrentJobUpdateError):
                store.save(stale)
            self.assertEqual(store.get(created["id"])["status"], "FIRST_UPDATE")

    def test_atomic_text_write_keeps_previous_file_when_replace_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scene.txt"
            path.write_text("stable\n", encoding="utf-8")
            with patch("webgal_backend.storage.os.replace", side_effect=OSError("injected replace failure")):
                with self.assertRaises(OSError):
                    write_text_atomic(path, "partial replacement\n")
            self.assertEqual(path.read_text(encoding="utf-8"), "stable\n")
            self.assertEqual(list(path.parent.glob(".scene.txt.*.tmp")), [])

    def test_job_store_migrates_legacy_json_and_uses_sqlite_as_primary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            jobs_dir = Path(tmp)
            job_id = "a" * 32
            job_dir = jobs_dir / job_id
            job_dir.mkdir(parents=True)
            legacy = {
                "id": job_id,
                "status": "CREATED",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "artifacts": {},
                "artifact_meta": {},
                "history": [],
            }
            write_json(job_dir / "job.json", legacy)
            store = JobStore(jobs_dir)
            self.assertEqual(store.get(job_id)["status"], "CREATED")

            legacy["status"] = "CORRUPTED_MIRROR"
            write_json(job_dir / "job.json", legacy)
            self.assertEqual(store.get(job_id)["status"], "CREATED")
            self.assertEqual([item["id"] for item in store.list_all()], [job_id])

    def test_job_store_repairs_missing_compatibility_mirror_on_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            jobs_dir = Path(tmp)
            store = JobStore(jobs_dir)
            job = store.create("source")
            store.job_file(job["id"]).unlink()
            reopened = JobStore(jobs_dir)
            self.assertTrue(reopened.job_file(job["id"]).is_file())
            self.assertEqual(read_json(reopened.job_file(job["id"]))["state_version"], job["state_version"])

    def test_job_store_marks_descendants_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp))
            job = store.create("source")
            write_json(store.artifact_path(job["id"], "state/narrative_plan.json"), {"version": 1})
            store.record_artifact(job, "narrative_plan", "state/narrative_plan.json")
            write_json(store.artifact_path(job["id"], "state/scene_plan.json"), {"version": 1})
            store.record_artifact(job, "scene_plan", "state/scene_plan.json")
            write_json(store.artifact_path(job["id"], "state/narrative_plan.json"), {"version": 2})
            store.record_artifact(job, "narrative_plan", "state/narrative_plan.json")
            metadata = store.get(job["id"])["artifact_meta"]
            self.assertEqual(metadata["scene_plan"]["status"], "stale")
            self.assertEqual(metadata["scene_plan"]["stale_because"], "narrative_plan")

    def test_job_execution_lock_rejects_duplicate_runner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp))
            job = store.create("source")
            token = store.reserve_execution(job["id"])
            try:
                with self.assertRaises(JobBusyError):
                    store.reserve_execution(job["id"])
            finally:
                with store.execution(job["id"], token):
                    pass

    def test_job_store_clears_inactive_run_reservation_on_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp))
            job = store.create("source")
            store.transition(job, "QUEUED", "NARRATIVE")
            job["active_run_id"] = "c" * 32
            store.save(job)
            self.assertEqual(store.clear_inactive_run_reservations(set()), 1)
            recovered = store.get(job["id"])
            self.assertEqual(recovered["status"], "FAILED")
            self.assertIsNone(recovered["active_run_id"])
            self.assertEqual(recovered["history"][-1]["event"], "STALE_RUN_RESERVATION_CLEARED")

    def test_durable_queue_rejects_duplicate_active_job_and_persists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "queue.sqlite3"
            queue = DurableTaskQueue(database)
            run_id = queue.enqueue("job-1", "phase", phase="scenes")
            with self.assertRaises(QueueBusyError):
                queue.enqueue("job-1", "phase", phase="validation")
            reopened = DurableTaskQueue(database)
            self.assertTrue(reopened.has_active("job-1"))
            task = reopened.claim_next("worker-1", lease_seconds=30)
            self.assertIsNotNone(task)
            self.assertEqual(task.id, run_id)
            self.assertTrue(reopened.heartbeat(run_id, "worker-1", lease_seconds=30))
            reopened.complete(run_id, "worker-1")
            self.assertEqual(reopened.get(run_id)["status"], "COMPLETED")
            self.assertFalse(reopened.has_active("job-1"))

    def test_prepared_task_is_not_claimable_and_abandoned_preparation_recovers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = DurableTaskQueue(Path(tmp) / "queue.sqlite3")
            run_id = queue.prepare("job-1", "phase", phase="scenes")
            self.assertTrue(queue.has_active("job-1"))
            self.assertIsNone(queue.claim_next("worker-1", lease_seconds=30))
            time.sleep(0.01)
            recovery = queue.recover_expired(preparing_timeout_seconds=0)
            self.assertEqual(recovery["abandoned_preparing_run_ids"], [run_id])
            self.assertEqual(queue.get(run_id)["status"], "FAILED")
            self.assertFalse(queue.has_active("job-1"))

    def test_queue_preparation_is_cancelled_when_job_state_save_fails(self) -> None:
        import webgal_backend.app as backend_app

        class FailingActiveRunStore(JobStore):
            fail_active_run_save = False

            def save(self, job: dict) -> None:
                if self.fail_active_run_save and job.get("active_run_id"):
                    raise RuntimeError("injected active_run_id save failure")
                super().save(job)

        original_store = backend_app.store
        original_queue = backend_app.task_queue
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                failing_store = FailingActiveRunStore(root / "jobs")
                queue = DurableTaskQueue(root / "queue.sqlite3")
                job = failing_store.create("source")
                failing_store.fail_active_run_save = True
                backend_app.store = failing_store
                backend_app.task_queue = queue
                with self.assertRaises(HTTPException) as raised:
                    _enqueue_job_task(job, "phase", phase="narrative")
                self.assertEqual(raised.exception.status_code, 503)
                runs = queue.list_for_job(job["id"])
                self.assertEqual(runs[0]["status"], "CANCELLED")
                saved = failing_store.get(job["id"])
                self.assertEqual(saved["status"], "FAILED")
                self.assertIsNone(saved.get("active_run_id"))
                self.assertFalse(queue.has_active(job["id"]))
        finally:
            backend_app.store = original_store
            backend_app.task_queue = original_queue

    def test_queued_task_refuses_to_run_without_matching_job_reservation(self) -> None:
        import webgal_backend.app as backend_app

        original_store = backend_app.store
        try:
            with tempfile.TemporaryDirectory() as tmp:
                backend_app.store = JobStore(Path(tmp) / "jobs")
                job = backend_app.store.create("source")
                task = QueuedTask(
                    id="b" * 32,
                    job_id=job["id"],
                    task_type="phase",
                    phase="narrative",
                    payload={},
                    attempts=1,
                )
                with self.assertRaises(PipelineError):
                    _execute_queued_task(task)
                self.assertEqual(backend_app.store.get(job["id"])["status"], "CREATED")
        finally:
            backend_app.store = original_store

    def test_durable_queue_recovers_expired_lease(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = DurableTaskQueue(Path(tmp) / "queue.sqlite3")
            run_id = queue.enqueue("job-1", "pipeline")
            claimed = queue.claim_next("dead-worker", lease_seconds=0)
            self.assertEqual(claimed.id, run_id)
            time.sleep(0.01)
            recovery = queue.recover_expired()
            self.assertEqual(recovery["requeued"], [run_id])
            reclaimed = queue.claim_next("new-worker", lease_seconds=30)
            self.assertEqual(reclaimed.id, run_id)
            self.assertEqual(reclaimed.attempts, 2)
            queue.complete(run_id, "new-worker")

    def test_durable_worker_executes_queued_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = DurableTaskQueue(Path(tmp) / "queue.sqlite3")
            completed = threading.Event()

            def handler(task):
                self.assertEqual(task.payload["value"], 7)
                completed.set()

            worker = DurableTaskWorker(queue, handler, lease_seconds=10, heartbeat_seconds=1)
            run_id = queue.enqueue("job-1", "test", payload={"value": 7})
            worker.start()
            worker.notify()
            self.assertTrue(completed.wait(timeout=3))
            deadline = time.time() + 3
            while queue.get(run_id)["status"] != "COMPLETED" and time.time() < deadline:
                time.sleep(0.01)
            worker.stop()
            self.assertEqual(queue.get(run_id)["status"], "COMPLETED")

    def test_config_generation_keeps_all_named_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp))
            job = store.create("source")
            pipeline = WebGALPipeline(store)
            game_dir = store.job_dir(job["id"]) / "public" / "game"
            (game_dir / "background" / "title.webp").write_bytes(b"image")
            (game_dir / "bgm" / "title.mp3").write_bytes(b"audio")
            store.job_file(job["id"]).unlink()
            pipeline._generate_config(store.job_dir(job["id"]), {"title": "Demo"})
            config = (game_dir / "config.txt").read_text(encoding="utf-8")
            self.assertEqual(config.count("Title_img:"), 1)
            self.assertIn("Title_img:title.webp;", config)
            self.assertIn("Title_bgm:title.mp3;", config)
            self.assertIn("Game_Logo:;", config)

    def test_publisher_keeps_old_revision_until_atomic_pointer_switch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)
            game_dir = job_dir / "public" / "game"
            scene_dir = game_dir / "scene"
            scene_dir.mkdir(parents=True)
            (game_dir / "config.txt").write_text("Game_name:Demo;\n", encoding="utf-8")
            start = scene_dir / "start.txt"
            start.write_text("intro:Version one;\n", encoding="utf-8")

            first = publish_game_revision(job_dir, source_revision=1)
            first_root = published_game_root(job_dir, fallback_to_working=False)
            self.assertEqual((first_root / "scene" / "start.txt").read_text(encoding="utf-8"), "intro:Version one;\n")

            start.write_text("intro:Unpublished work;\n", encoding="utf-8")
            self.assertEqual((published_game_root(job_dir, fallback_to_working=False) / "scene" / "start.txt").read_text(encoding="utf-8"), "intro:Version one;\n")

            second = publish_game_revision(job_dir, source_revision=2)
            self.assertNotEqual(first["revision_id"], second["revision_id"])
            self.assertEqual((published_game_root(job_dir, fallback_to_working=False) / "scene" / "start.txt").read_text(encoding="utf-8"), "intro:Unpublished work;\n")
            self.assertTrue((job_dir / "revisions" / first["revision_id"] / "public" / "game" / "scene" / "start.txt").exists())
            self.assertEqual(current_publication(job_dir)["revision_id"], second["revision_id"])

            revisions = list_game_revisions(job_dir)
            self.assertEqual([item["revision_id"] for item in revisions], [second["revision_id"], first["revision_id"]])
            self.assertTrue(revisions[0]["is_current"])
            restored = activate_game_revision(job_dir, first["revision_id"])
            self.assertEqual(restored["revision_id"], first["revision_id"])
            self.assertEqual(
                (published_game_root(job_dir, fallback_to_working=False) / "scene" / "start.txt").read_text(encoding="utf-8"),
                "intro:Version one;\n",
            )

    def test_corrupted_revision_cannot_replace_current_publication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)
            game_dir = job_dir / "public" / "game"
            scene_dir = game_dir / "scene"
            scene_dir.mkdir(parents=True)
            (game_dir / "config.txt").write_text("Game_name:Demo;\n", encoding="utf-8")
            start = scene_dir / "start.txt"
            start.write_text("intro:First;\n", encoding="utf-8")
            first = publish_game_revision(job_dir, source_revision=1)
            start.write_text("intro:Second;\n", encoding="utf-8")
            second = publish_game_revision(job_dir, source_revision=2)

            old_snapshot = job_dir / "revisions" / first["revision_id"] / "public" / "game" / "scene" / "start.txt"
            old_snapshot.write_text("intro:Tampered;\n", encoding="utf-8")
            with self.assertRaises(PublishError):
                activate_game_revision(job_dir, first["revision_id"])
            self.assertEqual(current_publication(job_dir)["revision_id"], second["revision_id"])

    def test_failed_publish_does_not_replace_current_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)
            game_dir = job_dir / "public" / "game"
            scene_dir = game_dir / "scene"
            scene_dir.mkdir(parents=True)
            config = game_dir / "config.txt"
            config.write_text("Game_name:Demo;\n", encoding="utf-8")
            (scene_dir / "start.txt").write_text("intro:Stable;\n", encoding="utf-8")
            published = publish_game_revision(job_dir, source_revision=1)
            config.unlink()
            with self.assertRaises(PublishError):
                publish_game_revision(job_dir, source_revision=2)
            self.assertEqual(current_publication(job_dir)["revision_id"], published["revision_id"])

    def test_validation_phase_publishes_only_after_passing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp))
            job = store.create("source", options=VALID_OPTIONS)
            job_dir = store.job_dir(job["id"])
            game_dir = job_dir / "public" / "game"
            scene_dir = game_dir / "scene"
            (game_dir / "config.txt").write_text("Game_name:Demo;\n", encoding="utf-8")
            (scene_dir / "start.txt").write_text("changeScene:ending_1.txt;\n", encoding="utf-8")
            (scene_dir / "ending_1.txt").write_text("end;\n", encoding="utf-8")
            pipeline = WebGALPipeline(store)
            pipeline.run_validation(job)
            saved = store.get(job["id"])
            self.assertEqual(saved["status"], "VALIDATION_PASSED")
            self.assertTrue(saved["published_revision"].startswith("r"))
            self.assertEqual(current_publication(job_dir)["revision_id"], saved["published_revision"])

    def test_job_store_rejects_non_uuid_job_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp))
            with self.assertRaises(FileNotFoundError):
                store.job_dir("..")
            with self.assertRaises(FileNotFoundError):
                store.job_dir("not-a-job-id")


if __name__ == "__main__":
    unittest.main()
