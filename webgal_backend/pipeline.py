from __future__ import annotations

import shutil
import subprocess
import os
from pathlib import Path
from typing import Any, Callable

from .config import settings
from .contract_context import build_phase_context
from .llm import OpenAIFunctionClient
from .prompts import SYSTEM_PROMPT, asset_prompt, narrative_prompt, repair_prompt, scene_prompt
from .storage import JobStore, read_json, write_json
from .validators import (
    ValidationFailure,
    deterministic_validate,
    semantic_asset_manifest,
    semantic_narrative,
    semantic_scene_batch,
    validate_schema,
)


class PipelineError(RuntimeError):
    pass


class WebGALPipeline:
    def __init__(self, store: JobStore | None = None, llm_factory: Callable[[], OpenAIFunctionClient] = OpenAIFunctionClient) -> None:
        self.store = store or JobStore()
        self.llm_factory = llm_factory

    def run_all(self, job_id: str) -> dict[str, Any]:
        job = self.store.get(job_id)
        try:
            self.run_narrative(job)
            self.run_assets(job)
            self.run_scenes(job)
            self.run_validation(job)
            self.run_repairs_until_clean(job)
            self.store.transition(job, "DONE", None)
            return self.store.get(job_id)
        except Exception as exc:
            self.store.set_error(job, str(exc))
            raise

    def run_phase(self, job_id: str, phase: str) -> dict[str, Any]:
        job = self.store.get(job_id)
        phases = {
            "narrative": self.run_narrative,
            "assets": self.run_assets,
            "scenes": self.run_scenes,
            "validation": self.run_validation,
            "repair": self.run_one_repair_cycle,
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
        prompt = narrative_prompt(job["source_material"], job["options"])
        plan = self._call_with_validation(
            function_name="emit_narrative_plan",
            artifact_key="narrative_plan",
            schema_name="narrative_plan.schema.json",
            user_prompt=prompt,
            semantic_validator=semantic_narrative,
            artifact_normalizer=self._normalize_narrative_plan,
        )
        job_dir = self.store.job_dir(job["id"])
        write_json(job_dir / "state" / "narrative_plan.json", plan)
        self._write_legacy_plan_files(job_dir, plan)
        self.store.record_artifact(job, "narrative_plan", "state/narrative_plan.json")
        self.store.transition(job, "NARRATIVE_READY", "NARRATIVE_PLANNING")

    def run_assets(self, job: dict[str, Any]) -> None:
        self.store.transition(job, "RUNNING", "ASSET_PLANNING")
        job_dir = self.store.job_dir(job["id"])
        plan = self._read_required(job_dir / "state" / "narrative_plan.json")
        base_dir = str((job_dir / "public" / "game").resolve())
        prompt = asset_prompt(plan, base_dir, job["options"])
        manifest = self._call_with_validation(
            function_name="emit_asset_manifest",
            artifact_key="asset_manifest",
            schema_name="asset_manifest.schema.json",
            user_prompt=prompt,
            semantic_validator=lambda artifact: semantic_asset_manifest(artifact, plan, base_dir),
        )
        write_json(job_dir / "assets_manifest.json", manifest)
        self.store.record_artifact(job, "asset_manifest", "assets_manifest.json")

        if job["options"].get("generate_assets", False):
            self._run_asset_scripts(job_dir)

        self.store.transition(job, "ASSETS_READY", "ASSET_PLANNING")

    def run_scenes(self, job: dict[str, Any]) -> None:
        self.store.transition(job, "RUNNING", "SCENE_WRITING")
        job_dir = self.store.job_dir(job["id"])
        plan = self._read_required(job_dir / "state" / "narrative_plan.json")
        manifest = self._read_required(job_dir / "assets_manifest.json")
        existing_assets = self._list_existing_assets(job_dir)
        prompt = scene_prompt(plan, manifest, existing_assets, job["options"])
        fallback_error = None
        try:
            batch = self._call_with_validation(
                function_name="emit_scene_batch",
                artifact_key="scene_batch",
                schema_name="scene_batch.schema.json",
                user_prompt=prompt,
                semantic_validator=lambda artifact: semantic_scene_batch(artifact, plan, manifest),
            )
        except Exception as exc:
            fallback_error = str(exc)
            batch = self._fallback_scene_batch(plan, manifest)
            validate_schema("scene_batch.schema.json", batch)
            semantic_scene_batch(batch, plan, manifest)
        scene_dir = job_dir / "public" / "game" / "scene"
        scene_dir.mkdir(parents=True, exist_ok=True)
        rendered_scenes = self._render_scene_batch(plan, manifest, batch)
        for file_name, content in rendered_scenes.items():
            (scene_dir / file_name).write_text(content.rstrip() + "\n", encoding="utf-8")
        write_json(job_dir / "state" / "scene_batch.json", batch)
        if fallback_error:
            write_json(
                job_dir / "state" / "scene_generation_fallback.json",
                {
                    "reason": fallback_error,
                    "strategy": "Generated compact scene blueprints from narrative_plan and assets_manifest.",
                },
            )
            self.store.record_artifact(job, "scene_generation_fallback", "state/scene_generation_fallback.json")
        self.store.record_artifact(job, "scene_batch", "state/scene_batch.json")
        self._generate_config(job_dir, plan)
        self._copy_engine_skeleton(job_dir)
        self.store.transition(job, "SCENES_READY", "SCENE_WRITING")

    def run_validation(self, job: dict[str, Any]) -> None:
        self.store.transition(job, "RUNNING", "VALIDATING")
        job_dir = self.store.job_dir(job["id"])
        plan = self._read_required(job_dir / "state" / "narrative_plan.json")
        manifest = self._read_required(job_dir / "assets_manifest.json")
        report = deterministic_validate(
            job_dir,
            plan,
            manifest,
            allow_missing_assets=bool(job["options"].get("allow_missing_assets", True)),
        )
        validate_schema("validation_report.schema.json", report)
        write_json(job_dir / "state" / "validation_report.json", report)
        self.store.record_artifact(job, "validation_report", "state/validation_report.json")
        status = "VALIDATION_PASSED" if report["summary"]["passed"] else "VALIDATION_FAILED"
        self.store.transition(job, status, "VALIDATING")

    def run_repairs_until_clean(self, job: dict[str, Any]) -> None:
        for _ in range(settings.max_repair_cycles):
            report = self._read_required(self.store.job_dir(job["id"]) / "state" / "validation_report.json")
            if report["summary"]["errors"] == 0:
                return
            self.run_one_repair_cycle(job)
            self.run_validation(job)

        report = self._read_required(self.store.job_dir(job["id"]) / "state" / "validation_report.json")
        if report["summary"]["errors"] > 0:
            raise PipelineError(f"repair stopped after {settings.max_repair_cycles} cycles with {report['summary']['errors']} errors")

    def run_one_repair_cycle(self, job: dict[str, Any]) -> None:
        self.store.transition(job, "RUNNING", "REPAIRING")
        job_dir = self.store.job_dir(job["id"])
        report = self._read_required(job_dir / "state" / "validation_report.json")
        if report["summary"]["errors"] == 0:
            self.store.transition(job, "REPAIR_SKIPPED", "REPAIRING")
            return

        plan = self._read_required(job_dir / "state" / "narrative_plan.json")
        manifest = self._read_required(job_dir / "assets_manifest.json")
        cycle = self._next_repair_cycle(job_dir)
        scenes = {
            f"public/game/scene/{path.name}": path.read_text(encoding="utf-8")
            for path in sorted((job_dir / "public" / "game" / "scene").glob("*.txt"))
        }
        prompt = repair_prompt(report, scenes, plan, manifest, cycle)
        repair_plan = self._call_with_validation(
            function_name="emit_repair_plan",
            artifact_key="repair_plan",
            schema_name="repair_plan.schema.json",
            user_prompt=prompt,
            semantic_validator=None,
        )
        self._apply_repair_plan(job_dir, repair_plan)
        self._append_repair_log(job_dir, repair_plan)
        self.store.transition(job, "REPAIR_APPLIED", "REPAIRING")

    def _call_with_validation(
        self,
        function_name: str,
        artifact_key: str,
        schema_name: str,
        user_prompt: str,
        semantic_validator: Callable[[dict[str, Any]], None] | None,
        artifact_normalizer: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        llm = self.llm_factory()
        last_error = ""
        prompt = user_prompt
        for attempt in range(settings.max_schema_retries + 1):
            phase_context = build_phase_context(function_name)
            system_prompt = f"{SYSTEM_PROMPT}\n\n{phase_context}"
            args = llm.call_function(function_name, system_prompt, prompt)
            if artifact_key not in args:
                last_error = f"function arguments missing key: {artifact_key}"
            else:
                artifact = args[artifact_key]
                if artifact_normalizer:
                    artifact = artifact_normalizer(artifact)
                try:
                    validate_schema(schema_name, artifact)
                    if semantic_validator:
                        semantic_validator(artifact)
                    return artifact
                except ValidationFailure as exc:
                    last_error = "\n".join(exc.errors)

            prompt = f"""{user_prompt}

The previous {function_name} call failed validation on attempt {attempt + 1}.
Return a corrected call to {function_name}.

Validation errors:
{last_error}

Do not explain. Call the function only."""

        raise PipelineError(f"{function_name} failed validation after retries:\n{last_error}")

    def _normalize_narrative_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        plan = dict(plan)
        scenes = [dict(scene) for scene in plan.get("scenes", [])]
        endings = [dict(ending) for ending in plan.get("endings", [])]

        for index, scene in enumerate(scenes):
            scene_id = scene.get("id") or f"scene_{index + 1}"
            scene["id"] = self._safe_id(scene_id)
            scene.setdefault("file", f"{scene['id']}.txt")
            scene["file"] = self._safe_scene_file(scene["file"], scene["id"])
            scene.setdefault("title", scene["id"].replace("_", " "))
            scene.setdefault("act", min(index, 9))
            scene.setdefault("description", scene.get("title", scene["id"]))
            scene.setdefault("purpose", scene.get("description", scene["id"]))
            scene.setdefault("is_entry", index == 0)
            scene.setdefault("is_ending", False)
            scene.setdefault("characters_present", [])

        scene_ids = {scene["id"] for scene in scenes}
        scene_files = {scene["file"] for scene in scenes}

        for priority, ending in enumerate(endings, start=1):
            ending_id = self._safe_id(ending.get("id") or f"ending_{priority}")
            ending["id"] = ending_id
            ending.setdefault("file", f"{ending_id}.txt")
            ending["file"] = self._safe_scene_file(ending["file"], ending_id)
            ending.setdefault("priority", priority)
            ending.setdefault("emotional_tone", ending.get("category", "default"))
            ending.setdefault("narrative_meaning", ending.get("emotional_tone", "ending"))
            ending.setdefault("trigger", {"type": "fallback", "conditions": [], "required_count": None})

            if ending_id not in scene_ids and ending["file"] not in scene_files:
                scenes.append(
                    {
                        "id": ending_id,
                        "file": ending["file"],
                        "title": ending_id.replace("_", " "),
                        "act": 9,
                        "description": ending.get("narrative_meaning", ending_id),
                        "purpose": "ending",
                        "is_entry": False,
                        "is_ending": True,
                        "characters_present": [],
                    }
                )
                scene_ids.add(ending_id)
                scene_files.add(ending["file"])

        if scenes and not any(scene.get("is_entry") for scene in scenes):
            scenes[0]["is_entry"] = True
        if sum(1 for scene in scenes if scene.get("is_entry")) > 1:
            first_entry_seen = False
            for scene in scenes:
                if scene.get("is_entry") and not first_entry_seen:
                    first_entry_seen = True
                else:
                    scene["is_entry"] = False

        plan["scenes"] = scenes
        plan["endings"] = endings
        return plan

    def _safe_id(self, value: Any) -> str:
        import re

        text = str(value or "item").lower()
        text = re.sub(r"[^a-z0-9_]+", "_", text).strip("_")
        if not text or not text[0].isalpha():
            text = f"item_{text or 'x'}"
        return text

    def _safe_scene_file(self, value: Any, fallback_id: str) -> str:
        name = str(value or f"{fallback_id}.txt").replace("\\", "/").split("/")[-1]
        if not name.endswith(".txt"):
            name = f"{name}.txt"
        stem = self._safe_id(name[:-4])
        return f"{stem}.txt"

    def _write_legacy_plan_files(self, job_dir: Path, plan: dict[str, Any]) -> None:
        state_dir = job_dir / "state"
        write_json(state_dir / "characters.json", {"characters": plan["characters"]})
        write_json(
            state_dir / "variables.json",
            {
                "attitude_variables": [
                    {
                        "id": item["id"],
                        "range": [item["min"], item["max"]],
                        "default": item["default"],
                        "description": item["description"],
                    }
                    for item in plan["variables"]["attitude"]
                ],
                "event_flags": [
                    {
                        "id": item["id"],
                        "values": item["values"],
                        "default": item["default"],
                        "description": item["description"],
                    }
                    for item in plan["variables"]["flags"]
                ],
            },
        )
        write_json(
            state_dir / "scene_graph.json",
            {
                "scenes": plan["scenes"],
                "connections": [
                    {
                        "from": item["from_scene_id"],
                        "to": item["to_scene_id"],
                        "condition": item["condition"],
                        "type": item["kind"],
                    }
                    for item in plan["connections"]
                ],
            },
        )
        write_json(
            state_dir / "branch_map.json",
            {
                "branches": [
                    {
                        "id": branch["id"],
                        "scene": branch["scene_id"],
                        "description": branch["description"],
                        "depth": branch["depth"],
                        "options": [
                            {
                                "label": option["label"],
                                "sets": {item["variable_id"]: item["value"] for item in option["sets"]},
                                "adds": {item["variable_id"]: item["value"] for item in option["adds"]},
                                "next_scene": option["next_scene_id"],
                            }
                            for option in branch["options"]
                        ],
                    }
                    for branch in plan["branches"]
                ]
            },
        )
        write_json(state_dir / "ending_matrix.json", {"endings": plan["endings"]})

    def _render_scene_batch(
        self,
        plan: dict[str, Any],
        manifest: dict[str, Any],
        batch: dict[str, Any],
    ) -> dict[str, str]:
        characters_by_id = {character["id"]: character for character in plan["characters"]}
        scene_by_id = {scene["id"]: scene for scene in plan["scenes"]}
        file_by_scene_id = {scene["id"]: scene["file"] for scene in plan["scenes"]}
        next_scene_by_id = self._default_next_scene_map(plan)
        ending_files = {ending["file"] for ending in plan["endings"]}
        figure_by_character = {
            image["source_ref"]["id"]: f"{image['filename']}.webp"
            for image in manifest["images"]
            if image["kind"] == "figure" and image["source_ref"]["type"] == "character"
        }

        rendered: dict[str, str] = {}
        for scene in batch["scenes"]:
            scene_meta = scene_by_id[scene["scene_id"]]
            character = characters_by_id[scene["speaker_character_id"]]
            figure = figure_by_character.get(scene["speaker_character_id"], "")
            miniavatar = f"miniavatar_{figure.removeprefix('figure_')}" if figure else ""
            is_ending = scene["file"] in ending_files or scene_meta.get("is_ending", False)
            next_scene_id = next_scene_by_id.get(scene["scene_id"])
            next_file = file_by_scene_id.get(next_scene_id, "ending_default.txt")

            lines = [
                f"; {scene_meta.get('title') or scene['scene_id']}",
                f"; Generated from schema blueprint: {scene['scene_id']}",
            ]

            if scene["file"] == "start.txt":
                for variable in plan["variables"]["attitude"] + plan["variables"]["flags"]:
                    lines.append(f"setVar:{variable['id']}={variable['default']};")

            lines.extend(
                [
                    f"changeBg:{scene['background_asset']} -next;",
                    "changeFigure:none -left -next;",
                    "changeFigure:none -right -next;",
                ]
            )

            if figure:
                lines.append(
                    f'changeFigure:{figure} -transform={{"scale":{{"x":0.7,"y":0.7}},"duration":700,"ease":"backOut"}} -next;'
                )

            if miniavatar:
                lines.append(f"miniAvatar:{miniavatar};")

            for index, beat in enumerate(scene["beats"], start=1):
                text = self._sanitize_webgal_text(beat["text"])
                if beat["kind"] == "dialogue":
                    lines.append(f"{character['name']}:{text}")
                else:
                    lines.append(f":{text}")
                if index % 4 == 0 and miniavatar:
                    lines.append(f"miniAvatar:{miniavatar};")

            while len(lines) < 30:
                lines.append(":风声渐缓，灯影在纸窗上轻轻摇动。")

            lines.extend(
                [
                    "changeFigure:none -left -next;",
                    "changeFigure:none -right -next;",
                ]
            )

            if is_ending:
                lines.append("end;")
            else:
                lines.append(f"callScene:{next_file};")
                lines.append(";")

            rendered[scene["file"]] = "\n".join(lines)

        return rendered

    def _fallback_scene_batch(self, plan: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
        protagonist_id = next(
            (character["id"] for character in plan["characters"] if character["role"] == "protagonist"),
            plan["characters"][0]["id"],
        )
        character_ids = {character["id"] for character in plan["characters"]}
        variable_ids = [variable["id"] for variable in plan["variables"]["attitude"] + plan["variables"]["flags"]]

        background_by_scene: dict[str, str] = {}
        backgrounds: list[str] = []
        figure_by_character: dict[str, str] = {}
        for image in manifest["images"]:
            filename = f"{image['filename']}.webp"
            if image["kind"] in {"background", "cg"}:
                backgrounds.append(filename)
                if image["source_ref"]["type"] == "scene":
                    background_by_scene[image["source_ref"]["id"]] = filename
            if image["kind"] == "figure" and image["source_ref"]["type"] == "character":
                figure_by_character[image["source_ref"]["id"]] = filename

        if not backgrounds:
            raise PipelineError("scene fallback requires at least one background or cg asset in assets_manifest.json")

        scenes = []
        for scene in plan["scenes"]:
            speaker_id = self._fallback_speaker(scene, protagonist_id, character_ids, figure_by_character)
            background = background_by_scene.get(scene["id"], backgrounds[0])
            referenced_assets = [background]
            figure = figure_by_character.get(speaker_id)
            if figure:
                referenced_assets.append(figure)
                referenced_assets.append(f"miniavatar_{figure.removeprefix('figure_')}")

            scenes.append(
                {
                    "scene_id": scene["id"],
                    "file": scene["file"],
                    "referenced_assets": referenced_assets,
                    "referenced_variables": variable_ids[: min(5, len(variable_ids))],
                    "background_asset": background,
                    "speaker_character_id": speaker_id,
                    "beats": self._fallback_beats(scene),
                }
            )

        return {"scenes": scenes}

    def _fallback_speaker(
        self,
        scene: dict[str, Any],
        protagonist_id: str,
        character_ids: set[str],
        figure_by_character: dict[str, str],
    ) -> str:
        for character_id in scene.get("characters_present", []):
            if character_id in character_ids and character_id in figure_by_character:
                return character_id
        for character_id in scene.get("characters_present", []):
            if character_id in character_ids:
                return character_id
        return protagonist_id

    def _fallback_beats(self, scene: dict[str, Any]) -> list[dict[str, str]]:
        title = self._clip_beat_text(scene.get("title") or scene["id"].replace("_", " "))
        description = self._clip_beat_text(scene.get("description") or title)
        purpose = self._clip_beat_text(scene.get("purpose") or description)
        ending_line = "这条道路在风雨之后抵达了属于自己的结局。" if scene.get("is_ending") else "新的抉择仍在前方等待。"
        raw_beats = [
            ("narration", f"{title}。"),
            ("narration", description),
            ("dialogue", "这一刻，我听见命运在门外停住了脚步。"),
            ("narration", purpose),
            ("dialogue", "若不能改变风雨，至少还要守住心中的火。"),
            ("narration", "沉默在屋檐下展开，像一张被雨水浸透的旧纸。"),
            ("dialogue", "我会记下这一夜，也记下仍未熄灭的愿望。"),
            ("narration", ending_line),
        ]
        return [{"kind": kind, "text": self._clip_beat_text(text)} for kind, text in raw_beats]

    def _clip_beat_text(self, text: Any) -> str:
        clean = str(text or "").replace("\r", " ").replace("\n", " ").strip()
        return clean[:180] if clean else "风雨仍在继续。"

    def _default_next_scene_map(self, plan: dict[str, Any]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for connection in plan["connections"]:
            if connection["kind"] == "callScene" and connection["condition"] is None:
                mapping.setdefault(connection["from_scene_id"], connection["to_scene_id"])

        ordered = sorted(plan["scenes"], key=lambda scene: (scene["act"], scene["file"]))
        non_endings = [scene for scene in ordered if not scene.get("is_ending")]
        file_to_scene_id = {scene["file"]: scene["id"] for scene in plan["scenes"]}
        default_ending = next(
            (
                file_to_scene_id.get(ending["file"], ending["id"])
                for ending in plan["endings"]
                if ending["category"] == "default"
            ),
            None,
        )

        for index, scene in enumerate(non_endings):
            if scene["id"] in mapping:
                continue
            if index + 1 < len(non_endings):
                mapping[scene["id"]] = non_endings[index + 1]["id"]
            elif default_ending:
                mapping[scene["id"]] = default_ending

        return mapping

    def _sanitize_webgal_text(self, text: str) -> str:
        return (
            text.replace("\r", " ")
            .replace("\n", " ")
            .replace(";", "；")
            .replace(":", "：")
            .strip()
        )

    def _generate_config(self, job_dir: Path, plan: dict[str, Any]) -> None:
        """Generate a config.txt for the WebGAL engine."""
        game_dir = job_dir / "public" / "game"
        game_dir.mkdir(parents=True, exist_ok=True)
        title = plan.get("title", "WebGAL Game")
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
            lines[2] = f"Title_img:{bg_files[0].name};"
        bgm_files = list((game_dir / "bgm").glob("*.mp3")) if (game_dir / "bgm").exists() else []
        if bgm_files:
            lines[3] = f"Title_bgm:{bgm_files[0].name};"
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

    def _list_existing_assets(self, job_dir: Path) -> list[str]:
        game_dir = job_dir / "public" / "game"
        return [
            str(path.relative_to(game_dir)).replace("\\", "/")
            for subdir in ["background", "figure", "bgm"]
            for path in (game_dir / subdir).glob("*")
            if path.is_file()
        ]

    def _read_required(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise PipelineError(f"required artifact missing: {path}")
        return read_json(path)

    def _next_repair_cycle(self, job_dir: Path) -> int:
        log_path = job_dir / "state" / "repair_log.json"
        if not log_path.exists():
            return 1
        return len(read_json(log_path)) + 1

    def _append_repair_log(self, job_dir: Path, repair_plan: dict[str, Any]) -> None:
        log_path = job_dir / "state" / "repair_log.json"
        log = read_json(log_path) if log_path.exists() else []
        log.append(repair_plan)
        write_json(log_path, log)

    def _apply_repair_plan(self, job_dir: Path, repair_plan: dict[str, Any]) -> None:
        for repair in repair_plan["repairs"]:
            if repair["strategy"] == "manual_required":
                continue
            path = (job_dir / repair["file"]).resolve()
            root = (job_dir / "public" / "game" / "scene").resolve()
            if root != path.parent:
                raise PipelineError(f"repair path outside scene directory: {repair['file']}")
            if not path.exists():
                raise PipelineError(f"repair target does not exist: {repair['file']}")
            text = path.read_text(encoding="utf-8")
            find = repair["find"]
            replace = repair["replace"] or ""
            strategy = repair["strategy"]

            if strategy == "replace_text":
                if not find or find not in text:
                    raise PipelineError(f"repair find text not found in {repair['file']}")
                text = text.replace(find, replace, 1)
            elif strategy == "insert_after":
                if not find or find not in text:
                    raise PipelineError(f"repair insertion anchor not found in {repair['file']}")
                text = text.replace(find, find + replace, 1)
            elif strategy == "insert_before":
                if not find or find not in text:
                    raise PipelineError(f"repair insertion anchor not found in {repair['file']}")
                text = text.replace(find, replace + find, 1)
            elif strategy == "append_block":
                text = text.rstrip() + "\n" + replace.rstrip() + "\n"
            else:
                raise PipelineError(f"unknown repair strategy: {strategy}")

            path.write_text(text, encoding="utf-8")
