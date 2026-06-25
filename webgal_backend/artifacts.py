from __future__ import annotations

from pathlib import Path
from typing import Any


NODE_ARTIFACTS = [
    {
        "key": "narrative_plan",
        "phase": "narrative",
        "phase_status": "NARRATIVE_PLANNING",
        "title": "故事大纲",
        "description": "故事进度、角色、冲突、结局和叙事结构。",
        "path": "state/narrative_plan.json",
        "content_type": "json",
    },
    {
        "key": "game_design",
        "phase": "game_design",
        "phase_status": "GAME_DESIGN",
        "title": "互动设计",
        "description": "按大纲展开的结构化场景、旁白、对白和互动节点。",
        "path": "state/game_design.json",
        "content_type": "json",
    },
    {
        "key": "scene_plan",
        "phase": "game_design",
        "phase_status": "GAME_DESIGN",
        "title": "场景模板",
        "description": "大纲阶段生成的统一场景文件、标题和类型映射。",
        "path": "state/scene_plan.json",
        "content_type": "json",
    },
    {
        "key": "game_design_completed",
        "phase": "game_design",
        "phase_status": "GAME_DESIGN",
        "title": "互动补全",
        "description": "追加分支后的结构化完整场景设计。",
        "path": "state/game_design_completed.json",
        "content_type": "json",
    },
    {
        "key": "game_design_choices",
        "phase": "game_design",
        "phase_status": "GAME_DESIGN_COMPLETION",
        "title": "分支选项",
        "description": "根据场景结构生成的选择与跳转 JSON。",
        "path": "state/game_design_choices.json",
        "content_type": "json",
    },
    {
        "key": "asset_manifest",
        "phase": "asset_manifest",
        "phase_status": "ASSET_PLANNING",
        "title": "素材规划",
        "description": "角色立绘、背景和素材文件规划。",
        "path": "assets_manifest.json",
        "content_type": "json",
    },
    {
        "key": "webgal_script",
        "phase": "script_rewrite",
        "phase_status": "SCRIPT_REWRITE",
        "title": "WebGAL 脚本",
        "description": "插入素材后的 WebGAL 可执行脚本文本。",
        "path": "state/game_design_webgal.txt",
        "content_type": "text",
    },
    {
        "key": "sound_effect_plan",
        "phase": "sound_effects",
        "phase_status": "SOUND_EFFECT_PLANNING",
        "title": "音效编排",
        "description": "音效插入规划。",
        "path": "state/sound_effect_plan.json",
        "content_type": "json",
    },
]


def contains_hidden_path(file_path: str) -> bool:
    return any(part.startswith(".") for part in file_path.replace("\\", "/").split("/") if part)


def normalize_artifact_path(relative_path: str) -> str:
    return relative_path.replace("\\", "/").lstrip("/")


def node_payload(job_dir: Path, item: dict[str, Any]) -> dict[str, Any]:
    path = job_dir / item["path"]
    payload = {**item, "exists": path.exists(), "content": None, "updated_at": None}
    if path.exists() and path.is_file():
        payload["content"] = path.read_text(encoding="utf-8")
        payload["updated_at"] = path.stat().st_mtime
    return payload


def scene_payloads(job_dir: Path) -> list[dict[str, Any]]:
    scene_dir = job_dir / "public" / "game" / "scene"
    if not scene_dir.exists():
        return []

    scenes = []
    for path in sorted(scene_dir.glob("*.txt")):
        relative = str(path.relative_to(job_dir)).replace("\\", "/")
        scenes.append(
            {
                "key": f"scene:{path.name}",
                "phase": "scenes",
                "phase_status": "SCENE_WRITING",
                "title": path.name,
                "description": "最终写入 WebGAL 的场景文件。",
                "path": relative,
                "content_type": "text",
                "exists": True,
                "content": path.read_text(encoding="utf-8"),
                "updated_at": path.stat().st_mtime,
            }
        )
    return scenes


def is_editable_artifact(relative: str) -> bool:
    if any(item["path"] == relative for item in NODE_ARTIFACTS):
        return True
    return relative.startswith("public/game/scene/") and relative.endswith(".txt")


def artifact_key_for_path(relative: str) -> str:
    for item in NODE_ARTIFACTS:
        if item["path"] == relative:
            return item["key"]
    return relative.replace("/", "_").replace(".", "_")
