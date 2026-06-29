from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


ArtifactContentType = Literal["json", "text"]


@dataclass(frozen=True)
class ArtifactDescriptor:
    key: str
    phase: str
    phase_status: str
    title: str
    description: str
    path: str
    content_type: ArtifactContentType

    def to_payload(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "phase": self.phase,
            "phase_status": self.phase_status,
            "title": self.title,
            "description": self.description,
            "path": self.path,
            "content_type": self.content_type,
        }


NODE_ARTIFACTS: tuple[ArtifactDescriptor, ...] = (
    ArtifactDescriptor(
        key="narrative_plan",
        phase="narrative",
        phase_status="NARRATIVE_PLANNING",
        title="\u6545\u4e8b\u5927\u7eb2",
        description="\u6545\u4e8b\u8fdb\u5ea6\u3001\u89d2\u8272\u3001\u51b2\u7a81\u3001\u7ed3\u5c40\u548c\u53d9\u4e8b\u7ed3\u6784\u3002",
        path="state/narrative_plan.json",
        content_type="json",
    ),
    ArtifactDescriptor(
        key="game_design",
        phase="game_design",
        phase_status="GAME_DESIGN",
        title="\u4e92\u52a8\u8bbe\u8ba1",
        description="\u6309\u5927\u7eb2\u5c55\u5f00\u7684\u7ed3\u6784\u5316\u573a\u666f\u3001\u65c1\u767d\u3001\u5bf9\u767d\u548c\u4e92\u52a8\u8282\u70b9\u3002",
        path="state/game_design.json",
        content_type="json",
    ),
    ArtifactDescriptor(
        key="scene_plan",
        phase="game_design",
        phase_status="GAME_DESIGN",
        title="\u573a\u666f\u6a21\u677f",
        description="\u5927\u7eb2\u9636\u6bb5\u751f\u6210\u7684\u7edf\u4e00\u573a\u666f\u6587\u4ef6\u3001\u6807\u9898\u548c\u7c7b\u578b\u6620\u5c04\u3002",
        path="state/scene_plan.json",
        content_type="json",
    ),
    ArtifactDescriptor(
        key="game_design_completed",
        phase="game_design",
        phase_status="GAME_DESIGN",
        title="\u4e92\u52a8\u8865\u5168",
        description="\u8ffd\u52a0\u5206\u652f\u540e\u7684\u7ed3\u6784\u5316\u5b8c\u6574\u573a\u666f\u8bbe\u8ba1\u3002",
        path="state/game_design_completed.json",
        content_type="json",
    ),
    ArtifactDescriptor(
        key="game_design_choices",
        phase="game_design",
        phase_status="GAME_DESIGN_COMPLETION",
        title="\u5206\u652f\u9009\u9879",
        description="\u6839\u636e\u573a\u666f\u7ed3\u6784\u751f\u6210\u7684\u9009\u62e9\u4e0e\u8df3\u8f6c JSON\u3002",
        path="state/game_design_choices.json",
        content_type="json",
    ),
    ArtifactDescriptor(
        key="asset_manifest",
        phase="asset_manifest",
        phase_status="ASSET_PLANNING",
        title="\u7d20\u6750\u89c4\u5212",
        description="\u89d2\u8272\u7acb\u7ed8\u3001\u80cc\u666f\u548c\u7d20\u6750\u6587\u4ef6\u89c4\u5212\u3002",
        path="assets_manifest.json",
        content_type="json",
    ),
    ArtifactDescriptor(
        key="webgal_script",
        phase="script_rewrite",
        phase_status="SCRIPT_REWRITE",
        title="WebGAL \u811a\u672c",
        description="\u63d2\u5165\u7d20\u6750\u540e\u7684 WebGAL \u53ef\u6267\u884c\u811a\u672c\u6587\u672c\u3002",
        path="state/game_design_webgal.txt",
        content_type="text",
    ),
    ArtifactDescriptor(
        key="sound_effect_plan",
        phase="sound_effects",
        phase_status="SOUND_EFFECT_PLANNING",
        title="\u97f3\u6548\u7f16\u6392",
        description="\u97f3\u6548\u63d2\u5165\u89c4\u5212\u3002",
        path="state/sound_effect_plan.json",
        content_type="json",
    ),
)

NODE_ARTIFACTS_BY_PATH = {item.path: item for item in NODE_ARTIFACTS}
NODE_ARTIFACTS_BY_KEY = {item.key: item for item in NODE_ARTIFACTS}

SCENE_ARTIFACT_DESCRIPTION = "\u6700\u7ec8\u5199\u5165 WebGAL \u7684\u573a\u666f\u6587\u4ef6\u3002"


def contains_hidden_path(file_path: str) -> bool:
    return any(part.startswith(".") for part in file_path.replace("\\", "/").split("/") if part)


def normalize_artifact_path(relative_path: str) -> str:
    return relative_path.replace("\\", "/").lstrip("/")


def node_payload(job_dir: Path, item: ArtifactDescriptor) -> dict[str, Any]:
    path = job_dir / item.path
    payload = {**item.to_payload(), "exists": path.exists(), "content": None, "updated_at": None}
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
                "description": SCENE_ARTIFACT_DESCRIPTION,
                "path": relative,
                "content_type": "text",
                "exists": True,
                "content": path.read_text(encoding="utf-8"),
                "updated_at": path.stat().st_mtime,
            }
        )
    return scenes


def is_editable_artifact(relative: str) -> bool:
    if relative in NODE_ARTIFACTS_BY_PATH:
        return True
    return relative.startswith("public/game/scene/") and relative.endswith(".txt")


def artifact_key_for_path(relative: str) -> str:
    item = NODE_ARTIFACTS_BY_PATH.get(relative)
    if item:
        return item.key
    return relative.replace("/", "_").replace(".", "_")
