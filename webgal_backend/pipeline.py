from __future__ import annotations

import shutil
import subprocess
import os
import time
import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

from .config import settings
from . import game_design
from .job_options import validate_generation_options
from .contract_context import build_phase_context
from .generation_limits import generation_limits
from .llm import LLMError, OpenAIFunctionClient
from .narrative_structure import NarrativeStructureError, repair_narrative_structure_if_needed
from .prompts import (
    SYSTEM_PROMPT,
    asset_prompt,
    game_design_completion_prompt,
    game_design_prompt,
    narrative_prompt,
    sound_effect_prompt,
    webgal_script_rewrite_prompt,
)
from .raw_correction import correct_generated_raw_file
from .scene_plan import build_scene_plan, expected_scene_files
from .storage import JobStore, read_json, utc_now, write_json
from .scene_validation import validate_and_repair_scenes, validation_report
from .tts_pipeline import build_tts_manifest, generate_tts_audio, write_tts_manifest
from .validators import (
    ValidationFailure,
    semantic_asset_manifest,
    validate_schema,
)


class PipelineError(RuntimeError):
    pass


@dataclass(frozen=True)
class PhaseSpec:
    handler_name: str
    validate_options: bool = True


PHASE_SPECS: dict[str, PhaseSpec] = {
    "narrative": PhaseSpec("run_narrative"),
    "game_design": PhaseSpec("run_game_design"),
    "game_design_draft": PhaseSpec("run_game_design_draft"),
    "game_design_completion": PhaseSpec("run_game_design_completion"),
    "asset_review": PhaseSpec("run_asset_review"),
    "asset_manifest": PhaseSpec("run_asset_manifest"),
    "asset_generation": PhaseSpec("run_asset_generation"),
    "script_rewrite": PhaseSpec("run_script_rewrite"),
    "sound_effects": PhaseSpec("run_sound_effects"),
    "sound": PhaseSpec("run_sound_effects"),
    "tts_generation": PhaseSpec("run_tts_generation"),
    "tts": PhaseSpec("run_tts_generation"),
    "assets": PhaseSpec("run_assets"),
    "game_build": PhaseSpec("run_game_build"),
    "scenes": PhaseSpec("run_scenes"),
    "validation": PhaseSpec("run_validation"),
}

RUN_ALL_PHASE_ORDER: tuple[str, ...] = (
    "narrative",
    "game_design",
    "asset_manifest",
    "script_rewrite",
    "sound_effects",
    "asset_generation",
    "scenes",
    "validation",
)


class WebGALPipeline:
    def __init__(self, store: JobStore | None = None, llm_factory: Callable[..., OpenAIFunctionClient] = OpenAIFunctionClient) -> None:
        self.store = store or JobStore()
        self.llm_factory = llm_factory

    @contextmanager
    def _trace_stage(
        self,
        job: dict[str, Any],
        stage_id: int,
        stage_name: str,
        artifact_key: str,
        artifact_path: str,
    ) -> Iterator[None]:
        started_at = utc_now()
        started = time.perf_counter()
        status = "completed"
        error = None
        try:
            yield
        except Exception as exc:
            status = "failed"
            error = str(exc)
            raise
        finally:
            ended_at = utc_now()
            duration_ms = round((time.perf_counter() - started) * 1000)
            self._append_stage_timing(
                job,
                {
                    "stage_id": stage_id,
                    "stage_name": stage_name,
                    "artifact_key": artifact_key,
                    "artifact_path": artifact_path,
                    "status": status,
                    "started_at": started_at,
                    "ended_at": ended_at,
                    "duration_ms": duration_ms,
                    "error": error,
                },
            )

    def _write_stage_event(
        self,
        job: dict[str, Any],
        stage_id: int,
        stage_name: str,
        artifact_key: str,
        status: str,
        message: str,
    ) -> None:
        self._append_stage_timing(
            job,
            {
                "stage_id": stage_id,
                "stage_name": stage_name,
                "artifact_key": artifact_key,
                "artifact_path": "",
                "status": status,
                "started_at": utc_now(),
                "ended_at": utc_now(),
                "duration_ms": 0,
                "message": message,
            },
        )

    def _append_stage_timing(self, job: dict[str, Any], event: dict[str, Any]) -> None:
        trace_dir = self.store.job_dir(job["id"]) / "state" / "llm_traces"
        trace_dir.mkdir(parents=True, exist_ok=True)
        path = trace_dir / "stage_timings.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            import json

            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        if job.get("artifacts", {}).get("stage_timings") != "state/llm_traces/stage_timings.jsonl":
            self.store.record_artifact(job, "stage_timings", "state/llm_traces/stage_timings.jsonl")

    def run_all(self, job_id: str) -> dict[str, Any]:
        job = self.store.get(job_id)
        try:
            validate_generation_options(job.get("options", {}))
            for phase in RUN_ALL_PHASE_ORDER:
                self._phase_handler(phase)(job)
            self.store.transition(job, "DONE", None)
            return self.store.get(job_id)
        except Exception as exc:
            self.store.set_error(job, str(exc))
            raise

    def phase_names(self) -> set[str]:
        return set(PHASE_SPECS)

    def _phase_handler(self, phase: str) -> Callable[[dict[str, Any]], None]:
        spec = PHASE_SPECS.get(phase)
        if spec is None:
            raise PipelineError(f"unknown phase: {phase}")
        return getattr(self, spec.handler_name)

    def run_phase(self, job_id: str, phase: str) -> dict[str, Any]:
        job = self.store.get(job_id)
        spec = PHASE_SPECS.get(phase)
        if spec is None:
            raise PipelineError(f"unknown phase: {phase}")
        try:
            if spec.validate_options:
                validate_generation_options(job.get("options", {}))
            self._phase_handler(phase)(job)
            return self.store.get(job_id)
        except Exception as exc:
            self.store.set_error(job, str(exc))
            raise

    def run_narrative(self, job: dict[str, Any]) -> None:
        self.store.transition(job, "RUNNING", "NARRATIVE_PLANNING")
        job_dir = self.store.job_dir(job["id"])
        with self._trace_stage(job, 1, "主题分析", "narrative_plan", "state/narrative_plan.json"):
            prompt = narrative_prompt(job["source_material"], job["options"])
            design = self._call_with_validation(
                job_dir=job_dir,
                function_name="emit_narrative_plan",
                artifact_key="narrative_plan",
                schema_name="narrative_plan.schema.json",
                user_prompt=prompt,
                artifact_normalizer=self._normalize_narrative_design,
                semantic_validator=self._validate_narrative_design,
            )
            try:
                design = repair_narrative_structure_if_needed(
                    narrative_plan=design,
                    job_dir=job_dir,
                    llm_factory=self.llm_factory,
                )
            except NarrativeStructureError as exc:
                raise PipelineError(str(exc)) from exc
            validate_schema("narrative_plan.schema.json", design)
            write_json(job_dir / "state" / "narrative_plan.json", design)
            self.store.record_artifact(job, "narrative_plan", "state/narrative_plan.json")
        self.store.transition(job, "NARRATIVE_READY", "NARRATIVE_PLANNING")

    def run_game_design(self, job: dict[str, Any]) -> None:
        self.run_game_design_draft(job)
        self.run_game_design_completion(job)

    def run_game_design_draft(self, job: dict[str, Any]) -> None:
        self.store.transition(job, "RUNNING", "GAME_DESIGN")
        job_dir, narrative_plan, scene_plan = self._game_design_context(job)
        try:
            llm = self.llm_factory(trace_dir=job_dir / "state" / "llm_traces")
        except TypeError:
            llm = self.llm_factory()
        system_prompt = f"""{SYSTEM_PROMPT}

Current phase: game_design_text
Return plain text only. Do not call tools. Do not wrap the result in Markdown fences."""
        with self._trace_stage(job, 2, "游戏结构设计", "game_design", "state/game_design.json"):
            prompt = game_design_prompt(narrative_plan, job["options"], scene_plan=scene_plan)
            game_design_text = llm.call_text("game_design_text", system_prompt, prompt)
            game_design_text = correct_generated_raw_file(game_design_text, narrative_plan)
            self._validate_game_design_coverage(game_design_text, scene_plan, "game_design.json")
            game_design_json = game_design.text_to_json(game_design_text, narrative_plan, scene_plan)
            write_json(job_dir / "state" / "game_design.json", game_design_json)
            self.store.record_artifact(job, "game_design", "state/game_design.json")
        self.store.transition(job, "GAME_DESIGN_DRAFT_READY", "GAME_DESIGN")

    def run_game_design_completion(self, job: dict[str, Any]) -> None:
        self.store.transition(job, "RUNNING", "GAME_DESIGN_COMPLETION")
        job_dir, narrative_plan, scene_plan = self._game_design_context(job)
        game_design_json = self._read_game_design_json(job_dir)
        try:
            llm = self.llm_factory(trace_dir=job_dir / "state" / "llm_traces")
        except TypeError:
            llm = self.llm_factory()
        system_prompt = f"""{SYSTEM_PROMPT}

Current phase: game_design_choices
Return JSON only. Do not call tools. Do not wrap the result in Markdown fences."""
        with self._trace_stage(job, 3, "互动补全", "design_completion", "state/game_design_completed.json"):
            game_design_outline = game_design.extract_outline(game_design_json, narrative_plan, scene_plan)
            completion_prompt = game_design_completion_prompt(narrative_plan, game_design_outline, job["options"], scene_plan=scene_plan)
            choices_text = llm.call_text("game_design_choices", system_prompt, completion_prompt)
            choices_payload = self._normalize_game_design_choices(
                llm.parse_json_text(choices_text, "game_design_choices"),
                scene_plan,
                game_design_outline,
            )
            write_json(job_dir / "state" / "game_design_choices.json", choices_payload)
            self.store.record_artifact(job, "game_design_choices", "state/game_design_choices.json")
            completed_json = game_design.apply_choices_to_json(game_design_json, choices_payload)
            write_json(job_dir / "state" / "game_design_completed.json", completed_json)
            self.store.record_artifact(job, "game_design_completed", "state/game_design_completed.json")
            completed_text = game_design.render_json(completed_json)
            self._validate_game_design_coverage(completed_text, scene_plan, "game_design_completed.json")
        self.store.transition(job, "GAME_DESIGN_READY", "GAME_DESIGN")

    def _game_design_context(self, job: dict[str, Any]) -> tuple[Path, dict[str, Any], dict[str, Any]]:
        job_dir = self.store.job_dir(job["id"])
        narrative_plan = self._read_required(job_dir / "state" / "narrative_plan.json")
        scene_plan = build_scene_plan(narrative_plan)
        write_json(job_dir / "state" / "scene_plan.json", scene_plan)
        self.store.record_artifact(job, "scene_plan", "state/scene_plan.json")
        return job_dir, narrative_plan, scene_plan

    def _read_game_design_json(self, job_dir: Path) -> dict[str, Any]:
        json_path = job_dir / "state" / "game_design.json"
        if json_path.exists():
            data = read_json(json_path)
            if isinstance(data, dict):
                return data
            raise PipelineError("game_design.json must be a JSON object")
        raise PipelineError("game_design.json is required before design completion")

    def _read_game_design_completed_text(self, job_dir: Path) -> str:
        json_path = job_dir / "state" / "game_design_completed.json"
        if json_path.exists():
            data = read_json(json_path)
            if isinstance(data, dict):
                return game_design.render_json(data)
            raise PipelineError("game_design_completed.json must be a JSON object")
        raise PipelineError("game_design_completed.json is required before this phase")

    def _normalize_game_design_choices(
        self,
        parsed: dict[str, Any],
        scene_plan: dict[str, Any],
        game_design_outline: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return game_design.normalize_choices(parsed, scene_plan, game_design_outline)
        except game_design.GameDesignError as exc:
            raise PipelineError(str(exc)) from exc

    def run_assets(self, job: dict[str, Any]) -> None:
        self.run_asset_manifest(job)
        self.run_script_rewrite(job)
        self.run_sound_effects(job)
        self.run_asset_generation(job)

    def run_asset_review(self, job: dict[str, Any]) -> None:
        self.run_asset_manifest(job)
        self.run_image_asset_generation(job)

    def run_game_build(self, job: dict[str, Any]) -> None:
        self.run_script_rewrite(job)
        self.run_sound_effects(job)
        self.run_tts_generation(job)
        self.run_scenes(job)
        self.run_validation(job)
        self.store.transition(job, "DONE", None)

    def run_asset_manifest(self, job: dict[str, Any]) -> None:
        self.store.transition(job, "RUNNING", "ASSET_PLANNING")
        job_dir = self.store.job_dir(job["id"])
        narrative_plan = self._read_required(job_dir / "state" / "narrative_plan.json")
        scene_plan = build_scene_plan(narrative_plan)
        game_design_text = game_design.render_json(self._read_game_design_json(job_dir))
        asset_context = self._asset_context_from_narrative_and_game_design(narrative_plan, game_design_text)
        base_dir = str((job_dir / "public" / "game").resolve())
        with self._trace_stage(job, 4, "素材准备", "asset_manifest", "assets_manifest.json"):
            prompt = asset_prompt(asset_context, base_dir, job["options"], game_design_text=game_design_text, narrative_plan=narrative_plan)
            manifest = self._call_with_validation(
                job_dir=job_dir,
                function_name="emit_asset_manifest",
                artifact_key="asset_manifest",
                schema_name="asset_manifest.schema.json",
                user_prompt=prompt,
                semantic_validator=lambda artifact: semantic_asset_manifest(artifact, asset_context, base_dir),
            )
            write_json(job_dir / "assets_manifest.json", manifest)
            self.store.record_artifact(job, "asset_manifest", "assets_manifest.json")
        self.store.transition(job, "ASSET_MANIFEST_READY", "ASSET_PLANNING")

    def run_image_asset_generation(self, job: dict[str, Any]) -> None:
        self.store.transition(job, "RUNNING", "ASSET_GENERATION")
        job_dir = self.store.job_dir(job["id"])
        if not (job_dir / "assets_manifest.json").exists():
            raise PipelineError("assets_manifest.json is required before image asset generation")
        image_enabled = bool(job["options"].get("generate_assets", False))
        if not image_enabled:
            self._write_stage_event(
                job,
                7,
                "素材生成",
                "generated_assets",
                "skipped",
                "generate_assets option is false",
            )
            self.store.transition(job, "ASSET_REVIEW_READY", "ASSET_GENERATION")
            return

        with self._trace_stage(job, 7, "素材生成", "generated_assets", "public/game/background/*.webp, public/game/figure/*.webp"):
            self._run_asset_scripts(job_dir)
        self.store.transition(job, "ASSET_REVIEW_READY", "ASSET_GENERATION")

    def run_asset_generation(self, job: dict[str, Any]) -> None:
        self.store.transition(job, "RUNNING", "ASSET_GENERATION")
        job_dir = self.store.job_dir(job["id"])
        if not (job_dir / "assets_manifest.json").exists():
            raise PipelineError("assets_manifest.json is required before asset generation")
        image_enabled = bool(job["options"].get("generate_assets", False))
        tts_enabled = bool(job["options"].get("generate_tts", job["options"].get("voice_enabled", False)))
        artifact_path = "public/game/background/*.webp, public/game/figure/*.webp, public/game/vocal/*.wav"

        if not image_enabled and not tts_enabled:
            self._write_stage_event(
                job,
                7,
                "素材生成",
                "generated_assets",
                "skipped",
                "generate_assets option is false and generate_tts/voice_enabled is false",
            )
            self.store.transition(job, "ASSET_GENERATION_READY", "ASSET_GENERATION")
            return

        with self._trace_stage(job, 7, "素材生成", "generated_assets", artifact_path):
            tasks = []
            with ThreadPoolExecutor(max_workers=2) as executor:
                if image_enabled:
                    tasks.append(("image_assets", executor.submit(self._run_asset_scripts, job_dir)))
                if tts_enabled:
                    tasks.append(("voice_assets", executor.submit(self._generate_tts_artifacts, job, job_dir)))
                errors: list[str] = []
                for label, future in tasks:
                    try:
                        future.result()
                    except Exception as exc:
                        errors.append(f"{label}: {exc}")
                if errors:
                    raise PipelineError("asset generation failed:\n" + "\n".join(errors))

        self.store.transition(job, "ASSET_GENERATION_READY", "ASSET_GENERATION")

    def regenerate_asset_image(self, job: dict[str, Any], filename: str, prompt: str | None = None) -> dict[str, Any]:
        self.store.transition(job, "RUNNING", "ASSET_GENERATION")
        job_dir = self.store.job_dir(job["id"])
        manifest_path = job_dir / "assets_manifest.json"
        if not manifest_path.exists():
            raise PipelineError("assets_manifest.json is required before regenerating an asset")

        manifest = read_json(manifest_path)
        if not isinstance(manifest, dict) or not isinstance(manifest.get("images"), list):
            raise PipelineError("assets_manifest.json must contain an images array")

        clean_filename = filename.removesuffix(".webp")
        image = next(
            (
                item
                for item in manifest["images"]
                if isinstance(item, dict) and str(item.get("filename", "")).removesuffix(".webp") == clean_filename
            ),
            None,
        )
        if not image:
            raise PipelineError(f"asset not found in assets_manifest.json: {filename}")

        if prompt is not None and prompt.strip():
            image["prompt"] = prompt.strip()
            write_json(manifest_path, manifest)
            self.store.record_artifact(job, "asset_manifest", "assets_manifest.json")

        single_manifest = {**manifest, "images": [image]}
        temp_manifest_path = job_dir / "state" / "asset_regeneration_manifest.json"
        write_json(temp_manifest_path, single_manifest)
        self._run_asset_script_manifest(job_dir, temp_manifest_path)

        if str(image.get("subdir", "")).strip() == generation_limits()["assets"]["figure_subdir"]:
            figure_path = job_dir / "public" / "game" / "figure" / f"{clean_filename}.webp"
            if figure_path.exists():
                scripts = settings.asset_scripts_dir
                self._run_script([scripts / "remove_bg.py", figure_path], job_dir)
                self._run_script([scripts / "make_avatar.py", figure_path], job_dir)

        self.store.transition(job, "ASSET_GENERATION_READY", "ASSET_GENERATION")
        return image

    def run_script_rewrite(self, job: dict[str, Any]) -> None:
        self.store.transition(job, "RUNNING", "SCRIPT_REWRITE")
        job_dir = self.store.job_dir(job["id"])
        manifest = self._read_required(job_dir / "assets_manifest.json")
        completed_text = self._read_game_design_completed_text(job_dir)

        syntax_path = settings.contracts_dir / "syntax.md"
        if not syntax_path.exists():
            raise PipelineError("webgal_backend/contracts/syntax.md is required for WebGAL script rewriting")

        assets = self._script_asset_lists(manifest)
        write_json(job_dir / "state" / "script_assets.json", assets)

        with self._trace_stage(job, 5, "插入素材", "webgal_script_rewrite", "state/game_design_webgal.txt"):
            try:
                llm = self.llm_factory(trace_dir=job_dir / "state" / "llm_traces")
            except TypeError:
                llm = self.llm_factory()

            system_prompt = f"""{SYSTEM_PROMPT}

Current phase: webgal_script_rewrite
Return plain text only. Do not call tools. Do not wrap the result in Markdown fences."""
            prompt = webgal_script_rewrite_prompt(
                syntax_md=syntax_path.read_text(encoding="utf-8"),
                game_design_completed_text=completed_text,
                background_assets=assets["background_assets"],
                figure_assets=assets["figure_assets"],
            )
            rewritten_text = llm.call_text("webgal_script_rewrite", system_prompt, prompt)
            rewritten_text = self._format_check_scene_headers(
                rewritten_text,
                completed_text,
                "game_design_webgal.txt",
            )
            (job_dir / "state" / "game_design_webgal.txt").write_text(rewritten_text.rstrip() + "\n", encoding="utf-8")
            self.store.record_artifact(job, "script_assets", "state/script_assets.json")
            self.store.record_artifact(job, "game_design_webgal", "state/game_design_webgal.txt")
        self.store.transition(job, "SCRIPT_REWRITE_READY", "SCRIPT_REWRITE")

    def run_sound_effects(self, job: dict[str, Any]) -> None:
        self.store.transition(job, "RUNNING", "SOUND_EFFECT_PLANNING")
        job_dir = self.store.job_dir(job["id"])
        original_text = self._read_game_design_completed_text(job_dir)
        webgal_path = job_dir / "state" / "game_design_webgal.txt"
        if not webgal_path.exists():
            raise PipelineError("game_design_webgal.txt is required before sound effect insertion")

        assets = self._load_sound_effect_assets()
        available_assets = [item for item in assets if isinstance(item, dict) and bool(item.get("available"))]
        write_json(job_dir / "state" / "sound_effect_assets.json", assets)
        self.store.record_artifact(job, "sound_effect_assets", "state/sound_effect_assets.json")

        if not available_assets:
            write_json(job_dir / "state" / "sound_effect_plan.json", [])
            self.store.record_artifact(job, "sound_effect_plan", "state/sound_effect_plan.json")
            self._write_stage_event(
                job,
                6,
                "音效编排",
                "sound_effect_plan",
                "skipped",
                f"sound effects directory unavailable or empty: {settings.sound_effects_dir}",
            )
            self.store.transition(job, "SOUND_EFFECTS_READY", "SOUND_EFFECT_PLANNING")
            return

        with self._trace_stage(job, 6, "音效编排", "sound_effect_plan", "state/sound_effect_plan.json"):
            try:
                llm = self.llm_factory(trace_dir=job_dir / "state" / "llm_traces")
            except TypeError:
                llm = self.llm_factory()

            system_prompt = f"""{SYSTEM_PROMPT}

Current phase: sound_effect_planning
Return valid JSON only. Do not call tools. Do not wrap the result in Markdown fences."""
            text = llm.call_text(
                "sound_effect_planning",
                system_prompt,
                sound_effect_prompt(original_text, available_assets),
                thinking="disabled",
            )
            plan = self._normalize_sound_effect_plan(self._parse_sound_effect_plan_text(text), available_assets)
            write_json(job_dir / "state" / "sound_effect_plan.json", plan)
            self.store.record_artifact(job, "sound_effect_plan", "state/sound_effect_plan.json")

            script_text = webgal_path.read_text(encoding="utf-8")
            inserted_text, insertion_report = self._insert_sound_effects(script_text, plan)
            webgal_path.write_text(inserted_text.rstrip() + "\n", encoding="utf-8")
            self._copy_sound_effect_files(job_dir, insertion_report)

        self.store.transition(job, "SOUND_EFFECTS_READY", "SOUND_EFFECT_PLANNING")

    def run_tts_generation(self, job: dict[str, Any]) -> None:
        self.store.transition(job, "RUNNING", "TTS_GENERATION")
        job_dir = self.store.job_dir(job["id"])
        with self._trace_stage(job, 7, "素材生成", "generated_vocals", "state/tts_manifest.json, public/game/vocal/*.wav"):
            self._generate_tts_artifacts(job, job_dir)
        self.store.transition(job, "TTS_READY", "TTS_GENERATION")

    def _generate_tts_artifacts(self, job: dict[str, Any], job_dir: Path) -> None:
        script_path = job_dir / "state" / "game_design_webgal.txt"
        if not script_path.exists():
            raise PipelineError("game_design_webgal.txt is required before TTS generation")
        if not (job_dir / "state" / "narrative_plan.json").exists():
            raise PipelineError("narrative_plan.json is required before TTS generation")

        limits = generation_limits().get("tts", {})
        enabled = bool(job["options"].get("generate_tts", job["options"].get("voice_enabled", False)))
        narrative_plan = self._read_required(job_dir / "state" / "narrative_plan.json")
        character_voices = self._assign_tts_voices(job_dir, narrative_plan, limits)
        manifest = build_tts_manifest(job_dir, character_voices=character_voices, selection_options=job["options"])
        manifest = generate_tts_audio(job_dir, manifest, enabled=enabled)
        write_tts_manifest(job_dir, manifest)
        self.store.record_artifact(job, "tts_manifest", "state/tts_manifest.json")
        self.store.record_artifact(job, "generated_vocals", "public/game/vocal/*.wav")
        failed = [item for item in manifest.get("items", []) if item.get("status") == "failed"]
        if enabled and failed:
            sample = "; ".join(f"{item.get('filename')}: {item.get('error')}" for item in failed[:3])
            raise PipelineError(f"TTS generation failed for {len(failed)} lines: {sample}")

    def _assign_tts_voices(
        self,
        job_dir: Path,
        narrative_plan: dict[str, Any],
        limits: dict[str, Any],
    ) -> dict[str, list[str]]:
        try:
            llm = self.llm_factory(trace_dir=job_dir / "state" / "llm_traces")
        except TypeError:
            llm = self.llm_factory()

        characters = [
            {
                "name": character.get("name", ""),
                "gender": character.get("gender", ""),
                "personality": character.get("personality", ""),
            }
            for character in narrative_plan.get("characters", [])
        ]
        prompt = f"""请根据角色信息和可选音色，为每个角色选择最合适的 TTS voice，并为每个角色写一句简短语气说明。

角色信息:
{json.dumps(characters, ensure_ascii=False, indent=2)}

可选音色:
{json.dumps(limits.get("voices", {}), ensure_ascii=False, indent=2)}

要求:
- 必须只从可选音色的 male/female 对象 key 中选择 voice。
- 优先匹配角色 gender，其次参考 personality 的年龄感、气质、社会身份和说话质感。
- 每个角色的 value 必须是长度为 2 的数组: [voice, 声线描述]。
- 声线描述不是剧情表演指导，不要写具体台词情绪、句尾、压迫感、人物立场或表演动作。
- 声线描述要像音色库标签，简短、抽象、可感知，描述口音、年龄感、气质、声线质地和听感。
- 声线描述参考风格:
  - 带部分北方口音。阳光、温暖、活力、朝气
  - 知性与温柔的碰撞
  - 温和舒缓的声线
  - 调皮捣蛋却充满童真
  - 岁月和旱烟浸泡过的质朴嗓音
  - 慵懒的，自然舒服、沉稳
- 顶层 JSON 直接使用角色名作为 key，不要包裹 character_voices 字段。
- 返回 JSON，不要解释，不要 Markdown。

返回格式:
{{
  "海瑞": ["Kai", "清正克制的中年男声，沉稳质朴"],
  "徐阶": ["Eldric Sage", "岁月和茶烟浸泡过的温和老者嗓音"],
  "王国师": ["Arthur", "温厚舒缓的中年男声，带旧友般的暖意"]
}}"""
        system_prompt = f"""{SYSTEM_PROMPT}

Current phase: tts_voice_assignment
Return valid JSON only. Do not call tools. Do not wrap the result in Markdown fences."""
        try:
            text = llm.call_text("tts_voice_assignment", system_prompt, prompt, thinking="disabled")
            parsed = llm.parse_json_text(text, "tts_voice_assignment")
            if isinstance(parsed, dict):
                return {
                    str(key): [str(value[0]), str(value[1])]
                    for key, value in parsed.items()
                    if isinstance(value, list) and len(value) == 2
                }
        except LLMError:
            pass
        return {}

    def run_scenes(self, job: dict[str, Any]) -> None:
        self.store.transition(job, "RUNNING", "SCENE_WRITING")
        job_dir = self.store.job_dir(job["id"])
        completed_design_path = job_dir / "state" / "game_design_webgal.txt"
        if not completed_design_path.exists():
            raise PipelineError("game_design_webgal.txt is required before scene writing")
        script_text = completed_design_path.read_text(encoding="utf-8")
        try:
            scene_files = self._split_game_design_completed_to_scene_files(job_dir, script_text)
        except PipelineError as exc:
            if "did not contain any Scene:/Ending: sections" not in str(exc):
                raise
            reference_text = self._read_game_design_completed_text(job_dir)
            repaired_text = self._restore_missing_scene_headers(
                script_text,
                reference_text,
            )
            if repaired_text == script_text:
                raise
            completed_design_path.write_text(repaired_text.rstrip() + "\n", encoding="utf-8")
            scene_files = self._split_game_design_completed_to_scene_files(job_dir, repaired_text)
        write_json(job_dir / "state" / "scene_files.json", {"files": scene_files})
        self.store.record_artifact(job, "scene_files", "state/scene_files.json")
        narrative_plan = self._read_required(job_dir / "state" / "narrative_plan.json")
        self._generate_config(job_dir, narrative_plan)
        self._copy_engine_skeleton(job_dir)
        self.store.transition(job, "SCENES_READY", "SCENE_WRITING")

    def run_validation(self, job: dict[str, Any]) -> None:
        self.store.transition(job, "RUNNING", "VALIDATING")
        job_dir = self.store.job_dir(job["id"])
        with self._trace_stage(job, 9, "校验阶段", "validation_report", "state/validation_report.json"):
            result = validate_and_repair_scenes(job_dir)
            report = validation_report(result)
            write_json(job_dir / "state" / "validation_report.json", report)
            self.store.record_artifact(job, "validation_report", "state/validation_report.json")
            if report["summary"]["errors"] > 0:
                self.store.transition(job, "VALIDATION_FAILED", "VALIDATING")
                raise PipelineError(f"validation failed with {report['summary']['errors']} errors")
        self.store.transition(job, "VALIDATION_PASSED", "VALIDATING")

    def _load_sound_effect_assets(self) -> list[dict[str, Any]]:
        path = settings.workspace_root / "webgal_backend" / "sound_effect_assets.json"
        if not path.exists():
            raise PipelineError(f"sound effect asset table is missing: {path}")
        assets = read_json(path)
        if not isinstance(assets, list):
            raise PipelineError("sound_effect_assets.json must be a JSON array")
        directory_exists = settings.sound_effects_dir.exists()
        available_files = {item.name for item in settings.sound_effects_dir.glob("*.mp3")} if directory_exists else set()
        normalized = []
        for item in assets:
            if not isinstance(item, dict):
                continue
            filename = str(item.get("filename", "")).strip()
            if not filename:
                continue
            entry = dict(item)
            entry["filename"] = filename
            entry["available"] = directory_exists and filename in available_files
            normalized.append(entry)
        return normalized

    def _parse_sound_effect_plan_text(self, text: str) -> Any:
        import json
        import re

        stripped = text.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            stripped = "\n".join(lines).strip()
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            match = re.search(r"(\[[\s\S]*\]|\{[\s\S]*\})", stripped)
            if not match:
                raise PipelineError("sound_effect_planning returned invalid JSON")
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError as exc:
                raise PipelineError(f"sound_effect_planning returned invalid JSON: {exc}") from exc

    def _normalize_sound_effect_plan(self, raw_plan: Any, assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if isinstance(raw_plan, dict):
            raw_items = raw_plan.get("sound_effect_plan") or raw_plan.get("items") or raw_plan.get("effects") or []
        else:
            raw_items = raw_plan
        if not isinstance(raw_items, list):
            raise PipelineError("sound effect plan must be a JSON array")

        asset_by_name = {
            str(item.get("filename", "")): item
            for item in assets
            if isinstance(item, dict) and bool(item.get("available"))
        }
        allowed_categories = {"ambient", "movement", "event", "transition"}
        allowed_operations = {"start", "stop"}
        allowed_playback = {"once", "loop", "fadein_loop", "fadeout"}
        normalized: list[dict[str, Any]] = []
        seen_anchors: set[str] = set()

        for index, item in enumerate(raw_items):
            if not isinstance(item, dict):
                continue
            anchor = str(item.get("anchor", "")).strip()
            asset = str(item.get("asset", "")).strip()
            if not anchor or not asset or asset not in asset_by_name:
                continue
            if anchor in seen_anchors:
                continue
            category = str(item.get("category", asset_by_name[asset].get("category", "event"))).strip()
            operation = str(item.get("operation", "start")).strip()
            playback = str(item.get("playback", "once")).strip()
            if category not in allowed_categories:
                category = str(asset_by_name[asset].get("category", "event"))
            if operation not in allowed_operations:
                operation = "start"
            if playback not in allowed_playback:
                playback = "once"
            if playback == "fadeout":
                operation = "stop"
            if not bool(asset_by_name[asset].get("loopable", False)) and playback in {"loop", "fadein_loop"}:
                playback = "once"
            seen_anchors.add(anchor)
            normalized.append(
                {
                    "anchor": anchor,
                    "asset": asset,
                    "category": category if category in allowed_categories else "event",
                    "operation": operation,
                    "playback": playback,
                    "order": index,
                }
            )
        return normalized

    def _insert_sound_effects(self, script_text: str, plan: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
        lines = script_text.splitlines()
        inserted: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        used_line_indexes: set[int] = set()
        loop_ids: dict[str, str] = {}

        for item in plan:
            anchor = str(item.get("anchor", "")).strip()
            line_index = self._find_anchor_line(lines, anchor, used_line_indexes)
            if line_index is None:
                skipped.append({**item, "reason": "anchor_not_found"})
                continue
            command = self._sound_effect_command(item, loop_ids)
            if not command:
                skipped.append({**item, "reason": "unsupported_operation"})
                continue
            lines.insert(line_index, command)
            used_line_indexes = {index + 1 if index >= line_index else index for index in used_line_indexes}
            used_line_indexes.add(line_index + 1)
            inserted.append({**item, "line": line_index + 1, "command": command})
            if self._is_loop_sound_start(item):
                stop_command = self._loop_sound_stop_command(item)
                if stop_command:
                    stop_index = self._auto_stop_insert_index(lines, line_index + 1, story_line_count=4)
                    lines.insert(stop_index, stop_command)
                    used_line_indexes = {index + 1 if index >= stop_index else index for index in used_line_indexes}
                    inserted.append({**item, "line": stop_index + 1, "command": stop_command, "auto_stop": True})

        return "\n".join(lines), {"inserted": inserted, "skipped": skipped}

    def _find_anchor_line(self, lines: list[str], anchor: str, used_line_indexes: set[int]) -> int | None:
        if not anchor:
            return None
        for index, line in enumerate(lines):
            if index in used_line_indexes:
                continue
            if anchor in line:
                return index
        return None

    def _sound_effect_command(self, item: dict[str, Any], loop_ids: dict[str, str]) -> str | None:
        asset = str(item.get("asset", "")).strip()
        category = str(item.get("category", "event")).strip()
        operation = str(item.get("operation", "start")).strip()
        playback = str(item.get("playback", "once")).strip()
        sound_id = self._sound_effect_id(asset)
        if not sound_id:
            return None

        if operation == "stop" or playback == "fadeout":
            stop_id = loop_ids.get(category) or sound_id
            return f"playEffect:none -id={stop_id} -next;"

        volume = 55 if category == "ambient" else 75
        if playback in {"loop", "fadein_loop"}:
            loop_ids[category] = sound_id
            return f"playEffect:./game/vocal/{asset} -id={sound_id} -volume={volume} -next;"
        return f"playEffect:./game/vocal/{asset} -volume={volume} -next;"

    def _sound_effect_id(self, asset: str) -> str:
        import re

        return re.sub(r"[^a-zA-Z0-9_]+", "_", asset.removesuffix(".mp3")).strip("_").lower()[:48]

    def _is_loop_sound_start(self, item: dict[str, Any]) -> bool:
        operation = str(item.get("operation", "start")).strip()
        playback = str(item.get("playback", "once")).strip()
        return operation == "start" and playback in {"loop", "fadein_loop"}

    def _loop_sound_stop_command(self, item: dict[str, Any]) -> str | None:
        sound_id = self._sound_effect_id(str(item.get("asset", "")).strip())
        if not sound_id:
            return None
        return f"playEffect:none -id={sound_id} -next;"

    def _auto_stop_insert_index(self, lines: list[str], start_index: int, story_line_count: int) -> int:
        seen = 0
        for index in range(start_index, len(lines)):
            stripped = lines[index].strip()
            if self._is_scene_header(stripped) or self._is_scene_terminal_line(stripped):
                return index
            if self._is_sound_effect_story_line(stripped):
                seen += 1
                if seen >= story_line_count:
                    return index + 1
        return len(lines)

    def _is_scene_terminal_line(self, line: str) -> bool:
        return line.startswith(("end", "choose:", "changeScene:"))

    def _is_scene_header(self, line: str) -> bool:
        import re

        return bool(re.match(r"^(?:Scene|Ending)\s*:\s*[A-Za-z0-9_-]+\.txt\s*$", line, flags=re.IGNORECASE))

    def _is_sound_effect_story_line(self, line: str) -> bool:
        if not line or line.startswith((";", "//")) or self._is_scene_header(line):
            return False
        command_prefixes = (
            "change",
            "miniAvatar:",
            "setVar:",
            "unlock",
            "pixi",
            "bgm:",
            "playEffect:",
            "setTransition:",
            "choose:",
            "label:",
            "jumpLabel:",
            "callScene:",
            "end",
            "wait:",
        )
        return not line.startswith(command_prefixes)

    def _copy_sound_effect_files(self, job_dir: Path, insertion_report: dict[str, Any]) -> None:
        assets = {
            str(item.get("asset", "")).strip()
            for item in insertion_report.get("inserted", [])
            if str(item.get("asset", "")).strip()
        }
        if not assets:
            return
        if not settings.sound_effects_dir.exists():
            raise PipelineError(f"sound effects directory does not exist: {settings.sound_effects_dir}")
        target_dir = job_dir / "public" / "game" / "vocal"
        target_dir.mkdir(parents=True, exist_ok=True)
        for filename in assets:
            source = settings.sound_effects_dir / filename
            if not source.exists():
                raise PipelineError(f"sound effect file is missing: {source}")
            shutil.copy2(source, target_dir / filename)

    def _call_with_validation(
        self,
        job_dir: Path,
        function_name: str,
        artifact_key: str,
        schema_name: str,
        user_prompt: str,
        semantic_validator: Callable[[dict[str, Any]], None] | None,
        artifact_normalizer: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        try:
            llm = self.llm_factory(trace_dir=job_dir / "state" / "llm_traces")
        except TypeError:
            llm = self.llm_factory()
        last_error = ""
        prompt = user_prompt
        for attempt in range(settings.max_schema_retries + 1):
            phase_context = build_phase_context(function_name)
            system_prompt = f"{SYSTEM_PROMPT}\n\n{phase_context}"
            try:
                args = self._call_structured_llm(llm, function_name, artifact_key, system_prompt, prompt)
            except LLMError as exc:
                last_error = str(exc)
                prompt = f"""{user_prompt}

The previous {function_name} call failed on attempt {attempt + 1}.
Return corrected JSON for {artifact_key}.

Failure reason:
{last_error}

Keep every text field concise (1-2 short sentences). Do not explain."""
                continue
            if artifact_key not in args:
                last_error = f"function arguments missing key: {artifact_key}"
            else:
                artifact = args[artifact_key]
                try:
                    if artifact_normalizer:
                        artifact = artifact_normalizer(artifact)
                    validate_schema(schema_name, artifact)
                    if semantic_validator:
                        semantic_validator(artifact)
                    return artifact
                except ValidationFailure as exc:
                    last_error = "\n".join(exc.errors)

            prompt = f"""{user_prompt}

The previous {artifact_key} JSON failed validation on attempt {attempt + 1}.
Return corrected JSON for {artifact_key}.

Validation errors:
{last_error}

Do not explain."""

        raise PipelineError(f"{function_name} failed validation after retries:\n{last_error}")

    def _call_structured_llm(
        self,
        llm: OpenAIFunctionClient,
        function_name: str,
        artifact_key: str,
        system_prompt: str,
        prompt: str,
    ) -> dict[str, Any]:
        thinking = self._thinking_for_function(function_name)
        if self._use_json_text_for_function(function_name) and "deepseek.com" in settings.llm_base_url:
            text_prompt = f"""{prompt}

Return valid JSON only, without Markdown fences or explanation.
The top-level JSON object must have exactly this key: "{artifact_key}"."""
            text = llm.call_text(function_name, system_prompt, text_prompt, thinking=thinking)
            return llm.parse_json_text(text, function_name)
        return llm.call_function(function_name, system_prompt, prompt, thinking=thinking)

    def _thinking_for_function(self, function_name: str) -> str:
        if function_name in {"emit_narrative_plan", "emit_asset_manifest"}:
            return "disabled"
        return settings.llm_thinking

    def _use_json_text_for_function(self, function_name: str) -> bool:
        if function_name in {"emit_narrative_plan", "emit_asset_manifest"}:
            return True
        return settings.llm_thinking == "enabled"

    def _normalize_narrative_design(self, design: dict[str, Any]) -> dict[str, Any]:
        allowed_root_keys = {
            "title",
            "theme",
            "emotion_tone",
            "conflict_structure",
            "story_progression",
            "story_arc",
            "characters",
            "touchable_points",
            "must_avoid",
            "endings",
            "beat_structure",
            "narrative_structure",
        }
        for key in list(design.keys()):
            if key not in allowed_root_keys:
                design.pop(key, None)

        character_ids = {
            str(character.get("id", "")).strip()
            for character in design.get("characters", [])
            if isinstance(character, dict)
        }
        player_aliases = {"protagonist", "player", "main_character", "maincharacter", "mc", "hero", "heroine"}
        for character in design.get("characters", []):
            if not isinstance(character, dict):
                continue
            relationships = character.get("relationships", [])
            if not isinstance(relationships, list):
                continue
            character["relationships"] = [
                relationship
                for relationship in relationships
                if not (
                    isinstance(relationship, dict)
                    and str(relationship.get("with", "")).strip() in player_aliases
                    and str(relationship.get("with", "")).strip() not in character_ids
                )
            ]
        return design

    def _validate_narrative_design(self, design: dict[str, Any]) -> None:
        errors: list[str] = []
        character_ids = {character["id"] for character in design["characters"]}
        if not design["story_progression"]:
            errors.append("story_progression must not be empty")
        for character in design["characters"]:
            for relationship in character["relationships"]:
                if relationship["with"] not in character_ids:
                    errors.append(f"character {character['id']} relationship references unknown character {relationship['with']}")
                if relationship["with"] == character["id"]:
                    errors.append(f"character {character['id']} relationship cannot reference itself")
        if errors:
            raise ValidationFailure(errors)

    def _validate_game_design_coverage(
        self,
        text: str,
        scene_plan: dict[str, Any],
        artifact_name: str,
    ) -> None:
        expected_files = expected_scene_files(scene_plan)
        found_files = self._scene_headers(text)

        missing_files = [file_name for file_name in expected_files if file_name not in found_files]
        duplicate_files = sorted({file_name for file_name in found_files if found_files.count(file_name) > 1})
        if missing_files or duplicate_files:
            raise PipelineError(
                f"{artifact_name} coverage check failed: "
                f"missing_scene_files={missing_files}, duplicate_scene_files={duplicate_files}"
            )

    def _split_game_design_completed_to_scene_files(self, job_dir: Path, text: str) -> list[str]:
        import re

        matches = self._scene_header_matches(text)
        if not matches:
            raise PipelineError("script text did not contain any Scene:/Ending: sections")

        scene_dir = job_dir / "public" / "game" / "scene"
        scene_dir.mkdir(parents=True, exist_ok=True)
        written = []
        for index, match in enumerate(matches):
            body_start = match.end()
            body_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            file_name = match.group("filename").replace("\\", "/").split("/")[-1]
            if not re.match(r"^[A-Za-z0-9_-]+\.txt$", file_name):
                raise PipelineError(f"invalid scene filename in script text: {file_name}")
            content = text[body_start:body_end].strip()
            (scene_dir / file_name).write_text(content.rstrip() + "\n", encoding="utf-8")
            written.append(f"public/game/scene/{file_name}")
        return written

    def _scene_header_matches(self, text: str):
        import re

        pattern = re.compile(
            r"""^\s*
            (?:\#{1,6}\s*)?
            (?:
                (?P<kind>Scene|Ending)\s*[:：]\s*
                |
                (?:[\[【「『]\s*)?
                (?:(?:场景|文件|scene|file)(?:\s*[:：]\s*|\s+))?
            )
            (?P<filename>[A-Za-z0-9_-]+\.txt)
            (?:\s*[\]】」』])?
            \s*[:：]?\s*$
            """,
            flags=re.IGNORECASE | re.MULTILINE | re.VERBOSE,
        )
        return list(pattern.finditer(text))

    def _format_scene_header(self, filename: str) -> str:
        prefix = "Ending" if filename.replace("\\", "/").split("/")[-1].startswith("ending_") else "Scene"
        return f"{prefix}:{filename}"

    def _scene_headers(self, text: str) -> list[str]:
        return [match.group("filename") for match in self._scene_header_matches(text)]

    def _format_check_scene_headers(
        self,
        script_text: str,
        reference_text: str,
        artifact_name: str,
        allow_additional_headers: bool = False,
    ) -> str:
        reference_headers = self._scene_headers(reference_text)
        if not reference_headers:
            raise PipelineError(f"{artifact_name} format check failed: reference text has no scene headers")

        existing_headers = self._scene_headers(script_text)
        if self._scene_headers_match_reference(existing_headers, reference_headers, allow_additional_headers):
            return script_text

        if not allow_additional_headers and existing_headers:
            normalized_text = self._normalize_scene_sections_to_reference(script_text, reference_headers)
            if normalized_text is not None:
                normalized_headers = self._scene_headers(normalized_text)
                if normalized_headers == reference_headers:
                    return normalized_text

        repaired_text = self._restore_missing_scene_headers(script_text, reference_text)
        repaired_headers = self._scene_headers(repaired_text)
        if self._scene_headers_match_reference(repaired_headers, reference_headers, allow_additional_headers):
            return repaired_text

        missing = [header for header in reference_headers if header not in repaired_headers]
        extra = [header for header in repaired_headers if header not in reference_headers]
        duplicate_counts = {
            header: repaired_headers.count(header)
            for header in sorted(set(repaired_headers))
            if repaired_headers.count(header) > 1
        }
        raise PipelineError(
            f"{artifact_name} format check failed: scene headers do not match reference. "
            f"expected {len(reference_headers)}, got {len(repaired_headers)}, "
            f"missing={missing}, extra={extra}, duplicates={duplicate_counts}"
        )

    def _scene_headers_match_reference(
        self,
        headers: list[str],
        reference_headers: list[str],
        allow_additional_headers: bool,
    ) -> bool:
        if not allow_additional_headers:
            return headers == reference_headers

        cursor = 0
        for reference_header in reference_headers:
            try:
                cursor = headers.index(reference_header, cursor) + 1
            except ValueError:
                return False
        return True

    def _normalize_scene_sections_to_reference(self, script_text: str, reference_headers: list[str]) -> str | None:
        matches = self._scene_header_matches(script_text)
        if not matches:
            return None

        reference_set = set(reference_headers)
        sections: dict[str, str] = {}
        for index, match in enumerate(matches):
            header = match.group("filename")
            if header not in reference_set:
                return None
            if header in sections:
                continue
            body_start = match.end()
            body_end = matches[index + 1].start() if index + 1 < len(matches) else len(script_text)
            sections[header] = script_text[body_start:body_end].strip()

        if any(header not in sections for header in reference_headers):
            return None

        return "\n\n".join(
            f"{self._format_scene_header(header)}\n{sections[header]}".rstrip()
            for header in reference_headers
        )

    def _restore_missing_scene_headers(self, script_text: str, reference_text: str) -> str:
        import re

        existing_headers = self._scene_headers(script_text)
        reference_headers = self._scene_headers(reference_text)
        if existing_headers == reference_headers:
            return script_text

        if not reference_headers:
            return script_text

        headerless_script_text = self._remove_scene_header_lines(script_text) if existing_headers else script_text

        if not existing_headers:
            restored_from_anchors = self._restore_scene_headers_from_reference_anchors(script_text, reference_text)
            if restored_from_anchors is not None:
                return restored_from_anchors

        if headerless_script_text != script_text:
            restored_from_anchors = self._restore_scene_headers_from_reference_anchors(headerless_script_text, reference_text)
            if restored_from_anchors is not None:
                return restored_from_anchors

        restored_from_boundaries = self._restore_scene_headers_from_changefigure_setvar_boundaries(
            headerless_script_text,
            reference_headers,
        )
        if restored_from_boundaries is not None:
            return restored_from_boundaries

        chunks = [chunk.strip() for chunk in re.split(r"\r?\n\s*\r?\n", headerless_script_text.strip()) if chunk.strip()]
        if len(chunks) != len(reference_headers):
            raise PipelineError(
                "script text appears to have lost scene headers, "
                f"but cannot restore them safely: {len(reference_headers)} reference headers vs {len(chunks)} script blocks"
            )

        restored = []
        for header, chunk in zip(reference_headers, chunks, strict=True):
            restored.append(f"{self._format_scene_header(header)}\n{chunk}")
        return "\n\n".join(restored)

    def _remove_scene_header_lines(self, text: str) -> str:
        header_lines = {match.start() for match in self._scene_header_matches(text)}
        lines = text.splitlines()
        kept: list[str] = []
        offset = 0
        for line in lines:
            line_start = offset
            offset += len(line) + 1
            if line_start in header_lines:
                continue
            kept.append(line)
        return "\n".join(kept)

    def _restore_scene_headers_from_changefigure_setvar_boundaries(
        self,
        script_text: str,
        reference_headers: list[str],
    ) -> str | None:
        lines = script_text.splitlines()
        insert_indexes: list[int] = []

        for index in range(len(lines) - 1):
            current_line = lines[index].strip()
            next_line = lines[index + 1].strip()
            if (
                current_line.startswith("changeFigure:")
                and ".webp" in current_line
                and "-next" in current_line
                and next_line.startswith("setVar:")
            ):
                insert_indexes.append(index + 1)

        if len(insert_indexes) != len(reference_headers):
            return None

        restored_lines = list(lines)
        for insert_index, header in reversed(list(zip(insert_indexes, reference_headers, strict=True))):
            restored_lines.insert(insert_index, self._format_scene_header(header))
        return "\n".join(restored_lines)

    def _restore_scene_headers_from_reference_anchors(self, script_text: str, reference_text: str) -> str | None:
        import re

        reference_matches = self._scene_header_matches(reference_text)
        if not reference_matches:
            return None

        sections: list[tuple[str, str]] = []
        for index, match in enumerate(reference_matches):
            body_start = match.end()
            body_end = reference_matches[index + 1].start() if index + 1 < len(reference_matches) else len(reference_text)
            first_line = next(
                (line.strip() for line in reference_text[body_start:body_end].splitlines() if line.strip()),
                "",
            )
            if not first_line:
                return None
            sections.append((match.group("filename"), first_line))

        lines = script_text.splitlines()
        insert_indexes: list[int] = []
        cursor = 0
        for _header, anchor in sections:
            line_index = self._find_scene_anchor_line(lines, anchor, cursor)
            if line_index is None:
                return None
            insert_index = self._scene_insert_index_for_anchor(lines, line_index, cursor)
            insert_indexes.append(insert_index)
            cursor = line_index + 1

        if len(insert_indexes) != len(sections) or len(set(insert_indexes)) != len(insert_indexes):
            return None

        restored_lines = list(lines)
        for insert_index, (header, _anchor) in reversed(list(zip(insert_indexes, sections, strict=True))):
            restored_lines.insert(insert_index, self._format_scene_header(header))
        return "\n".join(restored_lines)

    def _find_scene_anchor_line(self, lines: list[str], anchor: str, cursor: int) -> int | None:
        import re

        variable_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*([+-])\s*(\d+)\s*;?$", anchor)
        if variable_match:
            variable, operator, amount = variable_match.groups()
            setvar_pattern = re.compile(
                rf"^\s*setVar:{re.escape(variable)}\s*=\s*{re.escape(variable)}\s*\{operator}\s*{re.escape(amount)}\s*;?\s*$"
            )
            for index in range(cursor, len(lines)):
                if setvar_pattern.match(lines[index].strip()):
                    return index
            return None

        for index in range(cursor, len(lines)):
            if lines[index].strip() == anchor:
                return index
        return None

    def _scene_insert_index_for_anchor(self, lines: list[str], line_index: int, cursor: int) -> int:
        insert_index = line_index
        while insert_index > cursor and self._is_scene_leading_command(lines[insert_index - 1].strip()):
            insert_index -= 1
        return insert_index

    def _is_scene_leading_command(self, line: str) -> bool:
        return line.startswith(("changeBg:", "changeFigure:", "playEffect:", "bgm:"))

    def _script_asset_lists(self, manifest: dict[str, Any]) -> dict[str, list[str]]:
        background_subdir = generation_limits()["assets"]["background_subdir"]
        figure_subdir = generation_limits()["assets"]["figure_subdir"]
        background_assets: list[str] = []
        figure_assets: list[str] = []
        for image in manifest.get("images", []):
            filename = str(image.get("filename", "")).strip()
            if not filename:
                continue
            asset_filename = filename if filename.lower().endswith(".webp") else f"{filename}.webp"
            subdir = image.get("subdir")
            if subdir == background_subdir:
                background_assets.append(asset_filename)
            elif subdir == figure_subdir:
                figure_assets.append(asset_filename)
        return {
            "background_assets": sorted(set(background_assets)),
            "figure_assets": sorted(set(figure_assets)),
        }

    def _asset_context_from_narrative_and_game_design(self, narrative_plan: dict[str, Any], game_design_text: str) -> dict[str, Any]:
        import re

        scenes = []
        for index, match in enumerate(self._scene_header_matches(game_design_text)):
            file_name = match.group("filename").replace("\\", "/").split("/")[-1]
            scene_id = self._safe_id(file_name.removesuffix(".txt"))
            scenes.append(
                {
                    "id": scene_id,
                    "file": file_name,
                    "title": scene_id.replace("_", " "),
                    "act": min(index, 9),
                    "description": scene_id.replace("_", " "),
                    "purpose": "asset_planning",
                    "is_entry": file_name == "start.txt",
                    "is_ending": file_name.startswith("ending_"),
                    "characters_present": [self._safe_id(character["id"]) for character in narrative_plan["characters"]],
                }
            )

        if not scenes:
            scenes.append(
                {
                    "id": "start",
                    "file": "start.txt",
                    "title": "start",
                    "act": 0,
                    "description": narrative_plan.get("story_arc", narrative_plan.get("theme", "")),
                    "purpose": "asset_planning",
                    "is_entry": True,
                    "is_ending": False,
                    "characters_present": [self._safe_id(character["id"]) for character in narrative_plan["characters"]],
                }
            )

        characters = [
            {
                "id": self._safe_id(character["id"]),
                "name": character["name"],
                "role": "protagonist" if index == 0 else "supporting",
                "personality": character["personality"],
                "motivation": character["motivation"],
                "internal_conflict": narrative_plan["conflict_structure"],
                "speech_style": character["speech_style"],
                "emotional_arc": character["emotional_arc"],
                "relationships": [],
            }
            for index, character in enumerate(narrative_plan["characters"])
        ]

        return {
            "metadata": {
                "title": narrative_plan["title"],
                "premise": narrative_plan["theme"],
                "tone": narrative_plan["emotion_tone"],
                "source_summary": narrative_plan["story_arc"],
            },
            "characters": characters,
            "scenes": scenes,
        }

    def _safe_id(self, value: Any) -> str:
        import re

        text = str(value or "item").lower()
        text = re.sub(r"[^a-z0-9_]+", "_", text).strip("_")
        if not text or not text[0].isalpha():
            text = f"item_{text or 'x'}"
        return text

    def _generate_config(self, job_dir: Path, plan: dict[str, Any]) -> None:
        """Generate a config.txt for the WebGAL engine."""
        game_dir = job_dir / "public" / "game"
        game_dir.mkdir(parents=True, exist_ok=True)
        title = plan.get("title") or plan.get("theme", {}).get("title") or "WebGAL Game"
        job_data = self._read_required(job_dir / "job.json")
        if title == "WebGAL Game":
            title = job_data.get("source_material", "WebGAL Game")[:30]
        game_key = plan.get("game_key", job_dir.name[:16])
        lines = [
            f"Game_name:{title};",
            f"Game_key:{game_key};",
            "Title_img:;",
            "Title_bgm:;",
            "Game_Logo:;",
        ]
        bg_files = list((game_dir / "background").glob("*.webp")) if (game_dir / "background").exists() else []
        if bg_files:
            lines[3] = f"Title_img:{bg_files[0].name};"
        bgm_files = list((game_dir / "bgm").glob("*.mp3")) if (game_dir / "bgm").exists() else []
        if bgm_files:
            lines[4] = f"Title_bgm:{bgm_files[0].name};"
        (game_dir / "config.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _copy_engine_skeleton(self, job_dir: Path) -> None:
        """Copy engine skeleton files (animation, template) to job's game directory."""
        source_game = settings.workspace_root / "public" / "game"
        target_game = job_dir / "public" / "game"
        for subdir in ["animation", "template"]:
            src = source_game / subdir
            dst = target_game / subdir
            if src.exists() and not dst.exists():
                shutil.copytree(src, dst)
        hotspots = target_game / "hotspots.json"
        if not hotspots.exists():
            hotspots.write_text("[]\n", encoding="utf-8")

    def _run_asset_scripts(self, job_dir: Path) -> None:
        manifest = job_dir / "assets_manifest.json"
        self._run_asset_script_manifest(job_dir, manifest)
        figures = sorted((job_dir / "public" / "game" / "figure").glob("figure_*.webp"))
        if figures:
            scripts = settings.asset_scripts_dir
            self._run_script([scripts / "remove_bg.py", *figures], job_dir)
            self._run_script([scripts / "make_avatar.py", *figures], job_dir)

    def _run_asset_script_manifest(self, job_dir: Path, manifest: Path) -> None:
        scripts = settings.asset_scripts_dir
        if not scripts.exists():
            raise PipelineError(f"asset scripts directory does not exist: {scripts}")

        (job_dir / "public" / "game").mkdir(parents=True, exist_ok=True)
        extra_env = {}
        ark_api_key = os.getenv("ARK_API_KEY")
        if ark_api_key:
            extra_env["ARK_API_KEY"] = ark_api_key

        self._run_script([scripts / "generate_assets.py", manifest], job_dir, extra_env=extra_env)

    def _run_script(self, args: list[Path], cwd: Path, extra_env: dict[str, str] | None = None) -> None:
        import sys
        command = [sys.executable, *[str(arg) for arg in args]]
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        result = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True, env=env)
        if result.returncode != 0:
            raise PipelineError(f"script failed: {' '.join(command)}\n{result.stderr or result.stdout}")

    def _read_required(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise PipelineError(f"required artifact missing: {path}")
        return read_json(path)
