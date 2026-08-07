from __future__ import annotations

import tempfile
import unittest
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from asset_scripts import generate_assets
from asset_scripts.generate_assets import MAX_WORKERS, _qwen_image_url, _qwen_size, _worker_count_for_model
from webgal_backend import game_design
from webgal_backend.artifacts import NODE_ARTIFACTS, artifact_key_for_path, is_editable_artifact
from webgal_backend.job_options import GenerationOptions, normalize_generation_options, validate_generation_options
from webgal_backend.app import _asset_review_item, _contains_hidden_path, _public_app_path
from webgal_backend.config import (
    DOUBAO_IMAGE_API_KEY_ENV,
    DOUBAO_IMAGE_MODEL,
    Settings,
    settings,
)
from webgal_backend.narrative_structure import narrative_structure_issues, repair_narrative_structure_if_needed
from webgal_backend.pipeline import PipelineError, WebGALPipeline
from webgal_backend.prompts import game_design_completion_prompt
from webgal_backend.raw_correction import correct_generated_raw_file, correct_inline_dialogue_direction
from webgal_backend.scene_plan import build_scene_plan, expected_ending_types, expected_scene_files, expected_source_nodes
from webgal_backend.scene_validation import _repair_scene_lines
from webgal_backend.scene_validation import _parse_choose_options, _scene_targets
from webgal_backend.storage import JobStore, read_json, write_json
from webgal_backend.tts_pipeline import (
    available_tts_voices,
    build_tts_manifest,
    build_tts_voice_review,
    selected_character_voices,
    select_tts_review_voice,
)
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

    def test_asset_review_urls_change_when_generated_files_are_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)
            figure_dir = job_dir / "public" / "game" / "figure"
            figure_dir.mkdir(parents=True)
            figure_path = figure_dir / "figure_main_role.webp"
            avatar_path = figure_dir / "miniavatar_main_role.webp"
            figure_path.write_bytes(b"first figure")
            avatar_path.write_bytes(b"first avatar")

            image = {
                "filename": "figure_main_role",
                "subdir": "figure",
                "size": "1024x1024",
                "prompt": "test prompt",
                "available_scene": "start.txt",
            }
            first = _asset_review_item("job-1", job_dir, image, {}, {})

            figure_stat = figure_path.stat()
            avatar_stat = avatar_path.stat()
            os.utime(
                figure_path,
                ns=(figure_stat.st_atime_ns, figure_stat.st_mtime_ns + 1_000_000_000),
            )
            os.utime(
                avatar_path,
                ns=(avatar_stat.st_atime_ns, avatar_stat.st_mtime_ns + 1_000_000_000),
            )
            second = _asset_review_item("job-1", job_dir, image, {}, {})

            self.assertNotEqual(first["url"], second["url"])
            self.assertNotEqual(first["avatar_url"], second["avatar_url"])
            self.assertEqual(second["url"], f"/play/job-1/game/figure/figure_main_role.webp?v={figure_path.stat().st_mtime_ns}")
            self.assertEqual(
                second["avatar_url"],
                f"/play/job-1/game/figure/miniavatar_main_role.webp?v={avatar_path.stat().st_mtime_ns}",
            )

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

    def test_requeued_failed_job_clears_previous_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp) / "jobs")
            job = store.create("lesson", dict(VALID_OPTIONS))
            store.transition(job, "RUNNING", "GAME_DESIGN")
            store.set_error(job, "temporary model failure")

            store.transition(job, "QUEUED", "GAME_DESIGN_DRAFT")

            requeued = store.get(job["id"])
            self.assertEqual(requeued["status"], "QUEUED")
            self.assertEqual(requeued["phase"], "GAME_DESIGN_DRAFT")
            self.assertIsNone(requeued["error"])

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

    def test_generation_options_select_text_model_and_default_to_deepseek(self) -> None:
        self.assertEqual(normalize_generation_options(dict(VALID_OPTIONS))["text_model"], "deepseek")

        mimo_options = dict(VALID_OPTIONS)
        mimo_options["text_model"] = "mimo"
        self.assertEqual(normalize_generation_options(mimo_options)["text_model"], "mimo")

        invalid_options = dict(VALID_OPTIONS)
        invalid_options["text_model"] = "unknown"
        with self.assertRaises(ValueError):
            validate_generation_options(invalid_options)

    def test_pipeline_passes_job_text_model_to_llm_factory(self) -> None:
        captured: dict = {}
        fake_llm = object()

        def factory(**kwargs):
            captured.update(kwargs)
            return fake_llm

        with tempfile.TemporaryDirectory() as tmp:
            pipeline = WebGALPipeline(llm_factory=factory)
            created = pipeline._make_llm(
                {"options": {"text_model": "mimo"}},
                Path(tmp),
            )

        self.assertIs(created, fake_llm)
        self.assertEqual(captured["provider"], "mimo")

    def test_generation_options_select_image_model_and_default_to_doubao(self) -> None:
        self.assertEqual(normalize_generation_options(dict(VALID_OPTIONS))["image_model"], "default")

        for model in ("qwen-image-2.0-pro", "qwen-image-2.0", "qwen-image-max"):
            options = dict(VALID_OPTIONS)
            options["image_model"] = model
            self.assertEqual(normalize_generation_options(options)["image_model"], model)

        invalid_options = dict(VALID_OPTIONS)
        invalid_options["image_model"] = "unconfigured-image-model"
        with self.assertRaises(ValueError):
            validate_generation_options(invalid_options)

    def test_legacy_generic_image_env_cannot_change_default_from_doubao(self) -> None:
        legacy_overrides = {
            "WEBGAL_IMAGE_BASE_URL": "https://dashscope.example.invalid/api/v1",
            "WEBGAL_IMAGE_MODEL": "qwen-image-2.0",
            "WEBGAL_IMAGE_API_KEY_ENV": "DASHSCOPE_API_KEY",
        }
        with patch("webgal_backend.config.load_dotenv"), patch.dict(os.environ, legacy_overrides):
            configured = Settings.from_env()

        self.assertEqual(configured.image_model, DOUBAO_IMAGE_MODEL)
        self.assertEqual(configured.image_api_key_env, DOUBAO_IMAGE_API_KEY_ENV)
        self.assertNotIn("dashscope.example.invalid", configured.image_base_url)

    def test_pipeline_resolves_qwen_image_models_to_shared_dashscope_provider(self) -> None:
        pipeline = WebGALPipeline()
        base_url, model, api_key_env = pipeline._image_generation_config(
            {"options": {"image_model": "qwen-image-max"}}
        )
        self.assertEqual(base_url, settings.qwen_image_base_url)
        self.assertEqual(model, "qwen-image-max")
        self.assertEqual(api_key_env, settings.qwen_image_api_key_env)

        default_config = pipeline._image_generation_config({"options": {"image_model": "default"}})
        self.assertEqual(
            default_config,
            (settings.image_base_url, settings.image_model, settings.image_api_key_env),
        )
        self.assertEqual(default_config[1], DOUBAO_IMAGE_MODEL)
        self.assertEqual(default_config[2], DOUBAO_IMAGE_API_KEY_ENV)

    def test_asset_script_manifest_model_follows_job_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)
            manifest_path = job_dir / "assets_manifest.json"
            write_json(
                manifest_path,
                {
                    "base_dir": str(job_dir / "public" / "game"),
                    "model": "qwen-image-2.0",
                    "images": [],
                },
            )
            pipeline = WebGALPipeline()
            with patch.object(pipeline, "_run_script") as run_script:
                pipeline._run_asset_script_manifest(
                    {"options": {"image_model": "default"}},
                    job_dir,
                    manifest_path,
                )

            self.assertEqual(read_json(manifest_path)["model"], DOUBAO_IMAGE_MODEL)
            run_script.assert_called_once()

    def test_asset_script_exits_nonzero_when_any_image_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "assets_manifest.json"
            write_json(
                manifest_path,
                {
                    "base_dir": str(Path(tmp) / "public" / "game"),
                    "model": DOUBAO_IMAGE_MODEL,
                    "images": [
                        {
                            "filename": "background_test",
                            "subdir": "background",
                            "prompt": "test",
                            "size": "1024x1024",
                        }
                    ],
                },
            )
            with (
                patch.object(generate_assets, "_api_key_from_env", return_value=("ARK_API_KEY", "test-key")),
                patch.object(generate_assets, "generate_image", return_value=False),
                patch.object(sys, "argv", ["generate_assets.py", str(manifest_path)]),
                self.assertRaises(SystemExit) as exited,
            ):
                generate_assets.main()

        self.assertEqual(exited.exception.code, 1)

    def test_qwen_image_request_adapts_size_and_native_response(self) -> None:
        self.assertEqual(_qwen_size("qwen-image-2.0-pro", "2560x1440"), "2560*1440")
        self.assertEqual(_qwen_size("qwen-image-max", "2560x1440"), "1664*928")
        self.assertEqual(_qwen_size("qwen-image-max", "1280x1920"), "1104*1472")
        self.assertEqual(
            _qwen_image_url(
                {
                    "output": {
                        "choices": [
                            {
                                "message": {
                                    "content": [{"image": "https://example.com/generated.png"}]
                                }
                            }
                        ]
                    }
                }
            ),
            "https://example.com/generated.png",
        )

    def test_qwen_image_generation_is_serial(self) -> None:
        self.assertEqual(_worker_count_for_model("qwen-image-2.0-pro"), 1)
        self.assertEqual(_worker_count_for_model("qwen-image-2.0"), 1)
        self.assertEqual(_worker_count_for_model("qwen-image-max"), 1)
        self.assertEqual(_worker_count_for_model("doubao-seedream-4-5-251128"), MAX_WORKERS)

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

    def test_mimo_asset_manifest_uses_json_text_instead_of_function_call(self) -> None:
        class FakeMiMO:
            provider = "mimo"

            def __init__(self) -> None:
                self.text_calls = 0

            def call_text(self, _trace_name: str, _system_prompt: str, user_prompt: str, thinking: str | None = None) -> str:
                self.text_calls += 1
                self.assert_prompt = user_prompt
                return json.dumps({"asset_manifest": {"images": []}})

            def parse_json_text(self, text: str, _trace_name: str) -> dict:
                return json.loads(text)

            def call_function(self, *_args, **_kwargs) -> dict:
                raise AssertionError("MiMo must not use function calling for asset manifests")

        fake = FakeMiMO()
        pipeline = WebGALPipeline()
        parsed, raw = pipeline._call_structured_llm(
            fake,
            "emit_asset_manifest",
            "asset_manifest",
            "system",
            "prompt",
        )

        self.assertEqual(fake.text_calls, 1)
        self.assertEqual(parsed, {"asset_manifest": {"images": []}})
        self.assertEqual(json.loads(raw), parsed)
        self.assertIn('exactly this key: "asset_manifest"', fake.assert_prompt)

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
            self.assertEqual(full_manifest["selection"]["scope"], "key_lines")
            self.assertLess(len([item for item in full_manifest["items"] if item["status"] == "pending"]), 7)

    def test_tts_voice_review_builds_one_preview_per_character_and_excludes_narrator(self) -> None:
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
                },
                {
                    "id": "friend",
                    "name": "Friend",
                    "gender": "female",
                    "personality": "warm",
                    "motivation": "help",
                    "speech_style": "gentle",
                    "emotional_arc": "steady",
                    "relationships": [],
                },
            ]
            write_json(job_dir / "state" / "narrative_plan.json", plan)
            (job_dir / "state" / "game_design_webgal.txt").write_text(
                "\n".join(
                    [
                        "Scene:start.txt",
                        "旁白: This line must not receive a voice preview.",
                        "Hero: Short.",
                        "Hero: This is a representative and measured preview sentence.",
                        "Friend: I will stay here and help you finish the work.",
                    ]
                ),
                encoding="utf-8",
            )

            review = build_tts_voice_review(
                job_dir,
                {"Hero": ["Ethan", "bright"], "Friend": ["Cherry", "warm"]},
            )

            self.assertEqual([item["speaker"] for item in review["characters"]], ["Hero", "Friend"])
            self.assertEqual(review["characters"][0]["voice"], "Ethan")
            self.assertIn("representative", review["characters"][0]["text"])
            self.assertTrue(review["available_voices"])

    def test_tts_preview_generation_uses_completed_design_before_webgal_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp))
            options = dict(VALID_OPTIONS)
            options.update({"voice_enabled": True, "generate_tts": True})
            job = store.create("lesson", options)
            job_dir = store.job_dir(job["id"])
            write_json(job_dir / "state" / "narrative_plan.json", minimal_narrative_plan())
            write_json(
                job_dir / "state" / "game_design_completed.json",
                {
                    "version": 1,
                    "scenes": [
                        {
                            "marker": "Scene",
                            "scene_file": "start.txt",
                            "lines": [
                                {
                                    "kind": "dialogue",
                                    "speaker": "主角",
                                    "text": "我必须先理解选择带来的真正后果。",
                                }
                            ],
                        }
                    ],
                },
            )
            pipeline = WebGALPipeline(store=store)
            pipeline._assign_tts_voices = lambda *_args, **_kwargs: {"主角": ["Cherry", "克制"]}

            with patch(
                "webgal_backend.pipeline.generate_tts_voice_previews",
                side_effect=lambda _job_dir, review: review,
            ):
                pipeline.run_tts_preview_generation(job)

            review = read_json(job_dir / "state" / "tts_voice_review.json")
            self.assertFalse((job_dir / "state" / "game_design_webgal.txt").exists())
            self.assertEqual(review["characters"][0]["speaker"], "主角")
            self.assertIn("真正后果", review["characters"][0]["text"])

    def test_valid_existing_asset_manifest_is_reused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp))
            job = store.create("lesson", dict(VALID_OPTIONS))
            job_dir = store.job_dir(job["id"])
            write_json(job_dir / "state" / "narrative_plan.json", minimal_narrative_plan())
            write_json(
                job_dir / "state" / "game_design.json",
                {
                    "version": 1,
                    "scenes": [
                        {
                            "marker": "Scene",
                            "scene_file": "start.txt",
                            "lines": [{"kind": "dialogue", "speaker": "主角", "text": "开始。"}],
                        }
                    ],
                },
            )
            write_json(
                job_dir / "assets_manifest.json",
                {
                    "base_dir": str((job_dir / "public" / "game").resolve()),
                    "model": settings.image_model,
                    "images": [
                        {
                            "filename": "figure_main_role",
                            "subdir": "figure",
                            "size": "1440x2560",
                            "prompt": "完整角色立绘，纯白背景，全身可见，彩色，统一美术风格。",
                            "available_scene": "",
                        }
                    ],
                },
            )

            pipeline = WebGALPipeline(store=store)
            self.assertTrue(pipeline._can_reuse_asset_manifest(job))
            with patch.object(
                pipeline,
                "run_asset_manifest",
                side_effect=AssertionError("a valid asset manifest must not be regenerated"),
            ):
                pipeline.run_asset_review(job)
            self.assertEqual(store.get(job["id"])["status"], "ASSET_REVIEW_READY")

    def test_tts_voice_review_uses_current_selection_without_confirmation(self) -> None:
        review = {
            "characters": [
                {
                    "speaker": "Hero",
                    "speaker_id": "hero",
                    "voice": "Ethan",
                    "tone": "bright",
                    "status": "completed",
                }
            ]
        }
        self.assertEqual(selected_character_voices(review), {"Hero": ["Ethan", "bright"]})

        changed = select_tts_review_voice(review, "Hero", "Moon")
        self.assertEqual(changed["status"], "pending")
        self.assertIn("moon", changed["filename"])
        self.assertEqual(
            selected_character_voices(review),
            {"Hero": ["Moon", next(option["description"] for option in available_tts_voices() if option["name"] == "Moon")]},
        )

    def test_tts_voice_review_rejects_cross_gender_voice(self) -> None:
        review = {
            "characters": [
                {
                    "speaker": "Hero",
                    "speaker_id": "hero",
                    "gender": "男",
                    "voice": "Ethan",
                    "tone": "bright",
                    "status": "completed",
                }
            ]
        }

        with self.assertRaisesRegex(ValueError, "gender does not match"):
            select_tts_review_voice(review, "Hero", "Cherry")

    def test_job_store_rejects_non_uuid_job_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp))
            with self.assertRaises(FileNotFoundError):
                store.job_dir("..")
            with self.assertRaises(FileNotFoundError):
                store.job_dir("not-a-job-id")


if __name__ == "__main__":
    unittest.main()
