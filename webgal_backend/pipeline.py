from __future__ import annotations

import shutil
import subprocess
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from .config import settings
from .contract_context import build_phase_context
from .generation_limits import generation_limits
from .llm import LLMError, OpenAIFunctionClient
from .prompts import (
    SYSTEM_PROMPT,
    asset_prompt,
    game_design_completion_prompt,
    game_design_prompt,
    narrative_prompt,
    webgal_script_rewrite_prompt,
)
from .raw_correction import correct_generated_raw_file
from .storage import JobStore, read_json, utc_now, write_json
from .scene_validation import validate_and_repair_scenes, validation_report
from .validators import (
    ValidationFailure,
    semantic_asset_manifest,
    validate_schema,
)


class PipelineError(RuntimeError):
    pass


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
            self.run_narrative(job)
            self.run_game_design(job)
            self.run_asset_manifest(job)
            self.run_asset_generation(job)
            self.run_script_rewrite(job)
            self.run_scenes(job)
            self.run_validation(job)
            self.store.transition(job, "DONE", None)
            return self.store.get(job_id)
        except Exception as exc:
            self.store.set_error(job, str(exc))
            raise

    def run_phase(self, job_id: str, phase: str) -> dict[str, Any]:
        job = self.store.get(job_id)
        phases = {
            "narrative": self.run_narrative,
            "game_design": self.run_game_design,
            "asset_manifest": self.run_asset_manifest,
            "asset_generation": self.run_asset_generation,
            "script_rewrite": self.run_script_rewrite,
            "assets": self.run_assets,
            "scenes": self.run_scenes,
            "validation": self.run_validation,
        }
        if phase not in phases:
            raise PipelineError(f"unknown phase: {phase}")
        try:
            phases[phase](job)
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
                semantic_validator=self._validate_narrative_design,
            )
            write_json(job_dir / "state" / "narrative_plan.json", design)
            self.store.record_artifact(job, "narrative_plan", "state/narrative_plan.json")
        self.store.transition(job, "NARRATIVE_READY", "NARRATIVE_PLANNING")

    def run_game_design(self, job: dict[str, Any]) -> None:
        self.store.transition(job, "RUNNING", "GAME_DESIGN")
        job_dir = self.store.job_dir(job["id"])
        narrative_plan = self._read_required(job_dir / "state" / "narrative_plan.json")
        try:
            llm = self.llm_factory(trace_dir=job_dir / "state" / "llm_traces")
        except TypeError:
            llm = self.llm_factory()
        system_prompt = f"""{SYSTEM_PROMPT}

Current phase: game_design_text
Return plain text only. Do not call tools. Do not wrap the result in Markdown fences."""
        with self._trace_stage(job, 2, "游戏结构设计", "game_design", "state/game_design.txt"):
            prompt = game_design_prompt(narrative_plan, job["options"])
            game_design_text = llm.call_text("game_design_text", system_prompt, prompt)
            (job_dir / "state" / "game_design.txt").write_text(game_design_text.rstrip() + "\n", encoding="utf-8")
            self.store.record_artifact(job, "game_design", "state/game_design.txt")
        with self._trace_stage(job, 3, "剧情设计", "design_completion", "state/game_design_completed.txt"):
            completion_prompt = game_design_completion_prompt(narrative_plan, game_design_text, job["options"])
            completed_text = llm.call_text("game_design_completion_text", system_prompt, completion_prompt)
            completed_text = correct_generated_raw_file(completed_text, narrative_plan)
            (job_dir / "state" / "game_design_completed.txt").write_text(completed_text.rstrip() + "\n", encoding="utf-8")
            self.store.record_artifact(job, "game_design_completed", "state/game_design_completed.txt")
        self.store.transition(job, "GAME_DESIGN_READY", "GAME_DESIGN")

    def run_assets(self, job: dict[str, Any]) -> None:
        self.run_asset_manifest(job)
        self.run_asset_generation(job)
        self.run_script_rewrite(job)

    def run_asset_manifest(self, job: dict[str, Any]) -> None:
        self.store.transition(job, "RUNNING", "ASSET_PLANNING")
        job_dir = self.store.job_dir(job["id"])
        narrative_plan = self._read_required(job_dir / "state" / "narrative_plan.json")
        game_design_path = job_dir / "state" / "game_design.txt"
        if not game_design_path.exists():
            raise PipelineError("game_design.txt is required before asset planning")
        game_design_text = game_design_path.read_text(encoding="utf-8")
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

    def run_asset_generation(self, job: dict[str, Any]) -> None:
        self.store.transition(job, "RUNNING", "ASSET_GENERATION")
        job_dir = self.store.job_dir(job["id"])
        if not (job_dir / "assets_manifest.json").exists():
            raise PipelineError("assets_manifest.json is required before asset generation")
        if job["options"].get("generate_assets", False):
            with self._trace_stage(job, 5, "素材生成", "generated_assets", "public/game/background/*.webp, public/game/figure/*.webp"):
                self._run_asset_scripts(job_dir)
        else:
            self._write_stage_event(job, 5, "素材生成", "generated_assets", "skipped", "generate_assets option is false")
        self.store.transition(job, "ASSET_GENERATION_READY", "ASSET_GENERATION")

    def run_script_rewrite(self, job: dict[str, Any]) -> None:
        self.store.transition(job, "RUNNING", "SCRIPT_REWRITE")
        job_dir = self.store.job_dir(job["id"])
        manifest = self._read_required(job_dir / "assets_manifest.json")
        completed_path = job_dir / "state" / "game_design_completed.txt"
        if not completed_path.exists():
            raise PipelineError("game_design_completed.txt is required before rewriting with assets")

        syntax_path = settings.contracts_dir / "syntax.md"
        if not syntax_path.exists():
            raise PipelineError("webgal_backend/contracts/syntax.md is required for WebGAL script rewriting")

        assets = self._script_asset_lists(manifest)
        write_json(job_dir / "state" / "script_assets.json", assets)

        with self._trace_stage(job, 6, "插入素材", "webgal_script_rewrite", "state/game_design_webgal.txt"):
            try:
                llm = self.llm_factory(trace_dir=job_dir / "state" / "llm_traces")
            except TypeError:
                llm = self.llm_factory()

            system_prompt = f"""{SYSTEM_PROMPT}

Current phase: webgal_script_rewrite
Return plain text only. Do not call tools. Do not wrap the result in Markdown fences."""
            prompt = webgal_script_rewrite_prompt(
                syntax_md=syntax_path.read_text(encoding="utf-8"),
                game_design_completed_text=completed_path.read_text(encoding="utf-8"),
                background_assets=assets["background_assets"],
                figure_assets=assets["figure_assets"],
            )
            rewritten_text = llm.call_text("webgal_script_rewrite", system_prompt, prompt)
            (job_dir / "state" / "game_design_webgal.txt").write_text(rewritten_text.rstrip() + "\n", encoding="utf-8")
            self.store.record_artifact(job, "script_assets", "state/script_assets.json")
            self.store.record_artifact(job, "game_design_webgal", "state/game_design_webgal.txt")
        self.store.transition(job, "SCRIPT_REWRITE_READY", "SCRIPT_REWRITE")

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
            if "did not contain any [scene.txt] sections" not in str(exc):
                raise
            reference_path = job_dir / "state" / "game_design_completed.txt"
            if not reference_path.exists():
                raise
            repaired_text = self._restore_missing_scene_headers(
                script_text,
                reference_path.read_text(encoding="utf-8"),
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
        with self._trace_stage(job, 7, "校验阶段", "validation_report", "state/validation_report.json"):
            result = validate_and_repair_scenes(job_dir)
            report = validation_report(result)
            write_json(job_dir / "state" / "validation_report.json", report)
            self.store.record_artifact(job, "validation_report", "state/validation_report.json")
            if report["summary"]["errors"] > 0:
                self.store.transition(job, "VALIDATION_FAILED", "VALIDATING")
                raise PipelineError(f"validation failed with {report['summary']['errors']} errors")
        self.store.transition(job, "VALIDATION_PASSED", "VALIDATING")

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
                    validate_schema(schema_name, artifact)
                    if artifact_normalizer:
                        artifact = artifact_normalizer(artifact)
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

    def _split_game_design_completed_to_scene_files(self, job_dir: Path, text: str) -> list[str]:
        import re

        matches = list(re.finditer(r"^\s*(?:\[([A-Za-z0-9_-]+\.txt)\]|([A-Za-z0-9_-]+\.txt))\s*$", text, flags=re.MULTILINE))
        if not matches:
            raise PipelineError("script text did not contain any [scene.txt] sections")

        scene_dir = job_dir / "public" / "game" / "scene"
        scene_dir.mkdir(parents=True, exist_ok=True)
        written = []
        for index, match in enumerate(matches):
            body_start = match.end()
            body_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            file_name = (match.group(1) or match.group(2)).replace("\\", "/").split("/")[-1]
            if not re.match(r"^[A-Za-z0-9_-]+\.txt$", file_name):
                raise PipelineError(f"invalid scene filename in script text: {file_name}")
            content = text[body_start:body_end].strip()
            (scene_dir / file_name).write_text(content.rstrip() + "\n", encoding="utf-8")
            written.append(f"public/game/scene/{file_name}")
        return written

    def _restore_missing_scene_headers(self, script_text: str, reference_text: str) -> str:
        import re

        existing_headers = re.findall(r"^\s*\[([A-Za-z0-9_-]+\.txt)\]\s*$", script_text, flags=re.MULTILINE)
        if existing_headers:
            return script_text

        reference_headers = re.findall(r"^\s*\[([A-Za-z0-9_-]+\.txt)\]\s*$", reference_text, flags=re.MULTILINE)
        if not reference_headers:
            return script_text

        chunks = [chunk.strip() for chunk in re.split(r"\r?\n\s*\r?\n", script_text.strip()) if chunk.strip()]
        if len(chunks) != len(reference_headers):
            raise PipelineError(
                "game_design_webgal.txt appears to have lost scene headers, "
                f"but cannot restore them safely: {len(reference_headers)} reference headers vs {len(chunks)} script blocks"
            )

        restored = []
        for header, chunk in zip(reference_headers, chunks, strict=True):
            restored.append(f"[{header}]\n{chunk}")
        return "\n\n".join(restored)

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
        for index, match in enumerate(re.finditer(r"^\s*\[([A-Za-z0-9_-]+\.txt)\]\s*$", game_design_text, flags=re.MULTILINE)):
            file_name = match.group(1).replace("\\", "/").split("/")[-1]
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

    def _run_asset_scripts(self, job_dir: Path) -> None:
        manifest = job_dir / "assets_manifest.json"
        scripts = settings.asset_scripts_dir
        if not scripts.exists():
            raise PipelineError(f"asset scripts directory does not exist: {scripts}")

        (job_dir / "public" / "game").mkdir(parents=True, exist_ok=True)
        ark_api_key = os.getenv("ARK_API_KEY")
        if ark_api_key:
            game_env = job_dir / "public" / "game" / ".env"
            game_env.write_text(f"ARK_API_KEY={ark_api_key}\n", encoding="utf-8")

        self._run_script([scripts / "generate_assets.py", manifest], job_dir)
        figures = sorted((job_dir / "public" / "game" / "figure").glob("figure_*.webp"))
        if figures:
            self._run_script([scripts / "remove_bg.py", *figures], job_dir)
            self._run_script([scripts / "make_avatar.py", *figures], job_dir)

    def _run_script(self, args: list[Path], cwd: Path) -> None:
        import sys
        command = [sys.executable, *[str(arg) for arg in args]]
        result = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True)
        if result.returncode != 0:
            raise PipelineError(f"script failed: {' '.join(command)}\n{result.stderr or result.stdout}")

    def _read_required(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise PipelineError(f"required artifact missing: {path}")
        return read_json(path)

