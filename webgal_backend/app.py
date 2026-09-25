from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import artifacts
from .artifacts import contains_hidden_path
from .auth import auth_mode, identity_from_request, job_belongs_to_identity, user_from_request
from .asset_library import AssetLibraryError, AssetLibraryUnavailable, asset_library
from .config import settings
from .job_options import GenerationOptions, normalize_generation_options
from .narrative_nodes import NarrativeNodeError, NarrativeNodeKind, generate_narrative_node as generate_narrative_node_payload
from .narrative_structure import build_synced_narrative_structure, narrative_structure_issues
from .pipeline import PipelineError, WebGALPipeline
from .published_flow import published_flow
from .particle_effects import (
    EFFECT_PRESETS,
    ParticleEffectError,
    available_effects,
    load_state as load_particle_effect_state,
    normalize_assignment,
    save_scene_assignment,
)
from .scene_plan import build_scene_plan
from .storage import JobStore, write_json


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logging.getLogger("uvicorn.error").info(
        "WebGAL paths: contracts_dir=%s asset_scripts_dir=%s",
        settings.contracts_dir,
        settings.asset_scripts_dir,
    )
    yield


app = FastAPI(title="WebGAL Forge", version="1.0.0", redirect_slashes=False, lifespan=lifespan)
store = JobStore()
pipeline = WebGALPipeline(store)
frontend_dir = settings.workspace_root / "forge_frontend"
engine_dist_dir = settings.workspace_root / "dist"
frontend_url = os.getenv("WEBGAL_FRONTEND_URL", "http://127.0.0.1:3001")


def _contains_hidden_path(file_path: str) -> bool:
    return contains_hidden_path(file_path)


def _public_base_path() -> str:
    path = (urlsplit(frontend_url).path or "").strip()
    if not path or path == "/":
        return ""
    return f"/{path.strip('/')}"


def _public_app_path(path: str) -> str:
    normalized = path if path.startswith("/") else f"/{path}"
    prefix = _public_base_path()
    if not prefix:
        return normalized
    if normalized == prefix or normalized.startswith(f"{prefix}/"):
        return normalized
    return f"{prefix}{normalized}"


def _get_job_or_404(job_id: str) -> dict[str, Any]:
    try:
        return store.get(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _identity_from_request(request: Request) -> dict[str, str]:
    return identity_from_request(request, settings.workspace_root)


def _job_belongs_to_identity(job: dict[str, Any], identity: dict[str, str]) -> bool:
    return job_belongs_to_identity(job, identity)


def _get_owned_job_or_404(job_id: str, request: Request) -> dict[str, Any]:
    identity = _identity_from_request(request)
    job = _get_job_or_404(job_id)
    if not _job_belongs_to_identity(job, identity):
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    return job


def _require_sso_user(request: Request) -> dict[str, Any]:
    user = user_from_request(request, settings.workspace_root)
    if user.get("auth_type") != "sso":
        raise HTTPException(status_code=403, detail="asset library requires a NarrativeOS account")
    return user


def _asset_library_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AssetLibraryUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    logger.exception("Asset library operation failed: %s", exc)
    return HTTPException(status_code=502, detail=str(exc))


def _job_dir_or_404(job_id: str) -> Path:
    try:
        return store.job_dir(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


class CreateJobRequest(BaseModel):
    source_material: str = Field(min_length=1)
    options: GenerationOptions


class RunJobRequest(BaseModel):
    background: bool = False


class ArtifactUpdateRequest(BaseModel):
    path: str = Field(min_length=1)
    content: str
    base_revision: int | None = Field(default=None, ge=0)


class TTSPreviewRequest(BaseModel):
    speaker: str = Field(min_length=1)
    voice: str = Field(min_length=1)


class GenerateNarrativeNodeRequest(BaseModel):
    kind: NarrativeNodeKind
    prompt: str = Field(min_length=1)
    narrative_plan: dict[str, Any] | None = None


class SyncNarrativeStructureRequest(BaseModel):
    narrative_plan: dict[str, Any]
    base_revision: int | None = Field(default=None, ge=0)


class AssetRegenerateRequest(BaseModel):
    filename: str = Field(min_length=1)
    prompt: str | None = None
    background: bool = True
    base_revision: int | None = Field(default=None, ge=0)


class AssetRemoveBackgroundRequest(BaseModel):
    filename: str = Field(min_length=1)
    base_revision: int | None = Field(default=None, ge=0)


class AvatarCropRequest(BaseModel):
    filename: str = Field(min_length=1)
    zoom: float = Field(default=1, ge=1, le=3)
    offset_x: float = Field(default=0, ge=-1, le=1)
    offset_y: float = Field(default=0, ge=-1, le=1)
    base_revision: int | None = Field(default=None, ge=0)


class SceneMusicOverrideRequest(BaseModel):
    scene_file: str = Field(min_length=1)
    asset: str | None = None
    base_revision: int | None = Field(default=None, ge=0)


class SceneEffectRequest(BaseModel):
    scene_file: str = Field(min_length=1)
    effect_id: str | None = None
    count: int | None = None
    speed: float | None = None
    scale: float | None = None
    angle: float | None = None
    opacity: float | None = None
    drift: float | None = None
    gravity: float | None = None
    rotation_speed: float | None = None
    layer: str | None = None
    blend_mode: str | None = None
    base_revision: int | None = Field(default=None, ge=0)


class ScenePresentationDraftRequest(BaseModel):
    music: dict[str, str | None] = Field(default_factory=dict)
    effects: dict[str, dict[str, Any] | None] = Field(default_factory=dict)
    base_revision: int | None = Field(default=None, ge=0)


def _internal_operation_error(operation: str, job_id: str, exc: Exception) -> HTTPException:
    """Log the traceback and give the UI a safe identifier for correlating it."""
    diagnostic_id = uuid.uuid4().hex[:12]
    logger.exception(
        "Forge operation failed: diagnostic_id=%s operation=%s job_id=%s error=%s",
        diagnostic_id,
        operation,
        job_id,
        exc,
    )
    return HTTPException(
        status_code=500,
        detail={
            "message": "服务端处理失败，请根据诊断编号查看后端日志。",
            "operation": operation,
            "diagnostic_id": diagnostic_id,
        },
    )


def _require_job_editable(job: dict[str, Any], base_revision: int | None = None) -> None:
    if job.get("status") in {"RUNNING", "QUEUED"}:
        raise HTTPException(status_code=409, detail="job is running; wait for it to finish before editing")
    current_revision = int(job.get("draft_revision", 0))
    if base_revision is not None and base_revision != current_revision:
        raise HTTPException(status_code=409, detail=f"draft revision changed: expected {base_revision}, current {current_revision}")


def _artifact_edit_scope(relative: str) -> str:
    if relative == "state/narrative_plan.json":
        return "outline"
    if relative == "assets_manifest.json":
        return "assets"
    if relative == "state/game_design_completed.json" or relative.startswith("public/game/scene/"):
        return "scenes"
    return "design"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/generation-options/schema")
def generation_options_schema() -> dict[str, Any]:
    return GenerationOptions.model_json_schema()


@app.get("/auth/me")
def auth_me(request: Request) -> dict[str, Any]:
    return user_from_request(request, settings.workspace_root)


@app.get("/auth/config")
def auth_config() -> dict[str, str]:
    """Expose only the active login mechanism so the frontend can render its entry."""
    return {"mode": auth_mode()}


@app.get("/assets")
def list_library_assets(
    request: Request,
    source_type: str | None = Query(default=None, pattern="^(GENERATED|UPLOADED|IMPORTED)$"),
    kind: str | None = Query(default=None, pattern="^(BACKGROUND|FIGURE|VOICE|BGM|SFX|OTHER)$"),
    cursor_created_at: str | None = None,
    cursor_id: str | None = None,
    limit: int = Query(default=30, ge=1, le=50),
) -> dict[str, Any]:
    user = _require_sso_user(request)
    try:
        return asset_library.list_assets(
            user_id=str(user["id"]), source_type=source_type, kind=kind,
            cursor_created_at=cursor_created_at, cursor_id=cursor_id, limit=limit,
        )
    except (AssetLibraryError, FileNotFoundError) as exc:
        raise _asset_library_http_error(exc) from exc


@app.get("/assets/files/{file_id}/url")
def get_library_asset_url(file_id: str, request: Request) -> dict[str, str]:
    user = _require_sso_user(request)
    try:
        return {"url": asset_library.signed_file_url(user_id=str(user["id"]), file_id=file_id)}
    except (AssetLibraryError, FileNotFoundError) as exc:
        raise _asset_library_http_error(exc) from exc


@app.get("/")
def index() -> RedirectResponse:
    return RedirectResponse(frontend_url)


@app.post("/jobs")
def create_job(request: CreateJobRequest, http_request: Request) -> dict[str, Any]:
    identity = _identity_from_request(http_request)
    return store.create(request.source_material, normalize_generation_options(request.options), identity=identity)


@app.get("/jobs")
def list_jobs(request: Request) -> dict[str, Any]:
    identity = _identity_from_request(request)
    jobs = [job for job in store.list(identity) if _job_belongs_to_identity(job, identity)]
    return {"jobs": jobs}


@app.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request) -> dict[str, Any]:
    return _get_owned_job_or_404(job_id, request)


@app.get("/jobs/{job_id}/nodes")
def get_job_nodes(job_id: str, request: Request) -> dict[str, Any]:
    job = _get_owned_job_or_404(job_id, request)
    job_dir = _job_dir_or_404(job_id)
    nodes = [artifacts.node_payload(job_dir, item) for item in artifacts.NODE_ARTIFACTS]
    return {"job": job, "nodes": nodes, "scenes": artifacts.scene_payloads(job_dir)}


@app.get("/jobs/{job_id}/published-flow")
def get_published_flow(job_id: str, request: Request) -> dict[str, Any]:
    job = _get_owned_job_or_404(job_id, request)
    if not job.get("has_published_build"):
        raise HTTPException(status_code=409, detail="尚无已发布游戏")
    return published_flow(_job_dir_or_404(job_id), job.get("published_revision", 0))


@app.patch("/jobs/{job_id}/artifacts")
def update_artifact(job_id: str, request: ArtifactUpdateRequest, http_request: Request) -> dict[str, Any]:
    if contains_hidden_path(request.path):
        raise HTTPException(status_code=404, detail="artifact not found")
    try:
        job = _get_owned_job_or_404(job_id, http_request)
        path = store.artifact_path(job_id, request.path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    relative = artifacts.normalize_artifact_path(request.path)
    if not artifacts.is_editable_artifact(relative):
        raise HTTPException(status_code=400, detail=f"artifact is not editable: {relative}")
    _require_job_editable(job, request.base_revision)

    if job.get("has_published_build") and relative == "state/game_design_completed.json" and path.exists():
        published_snapshot = store.artifact_path(job_id, "state/published_game_design_completed.json")
        if not published_snapshot.exists():
            published_snapshot.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, published_snapshot)

    try:
        if relative.endswith(".json"):
            content = json.loads(request.content)
            if relative == "state/game_design_completed.json" and isinstance(content, dict):
                from .game_design import repair_continuation_labels
                content = repair_continuation_labels(content)
            write_json(path, content)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(request.content.rstrip() + "\n", encoding="utf-8")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"invalid JSON: {exc}") from exc

    store.record_artifact(job, artifacts.artifact_key_for_path(relative), relative)
    store.mark_draft_changed(job, _artifact_edit_scope(relative))
    return {"job": _get_owned_job_or_404(job_id, http_request), "path": relative, "saved": True}


@app.post("/jobs/{job_id}/narrative-node")
def generate_narrative_node(job_id: str, request: GenerateNarrativeNodeRequest, http_request: Request) -> dict[str, Any]:
    provider = "deepseek"
    try:
        job = _get_owned_job_or_404(job_id, http_request)
        provider = str(job.get("options", {}).get("text_model", "deepseek"))
        plan = request.narrative_plan or _read_narrative_plan(job_id)
        node = generate_narrative_node_payload(
            job_dir=store.job_dir(job_id),
            llm_factory=pipeline._llm_factory_for_job(job),
            kind=request.kind,
            user_prompt=request.prompt,
            narrative_plan=plan,
        )
        return {"kind": request.kind, "node": node, "provider": provider}
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (NarrativeNodeError, ValueError, PipelineError) as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": str(exc),
                "operation": "narrative_node_generate",
                "provider": provider,
            },
        ) from exc
    except Exception as exc:
        raise _internal_operation_error("narrative_node_generate", job_id, exc) from exc


@app.post("/jobs/{job_id}/narrative-structure/sync")
def sync_narrative_structure(job_id: str, request: SyncNarrativeStructureRequest, http_request: Request) -> dict[str, Any]:
    try:
        job = _get_owned_job_or_404(job_id, http_request)
        _require_job_editable(job, request.base_revision)
        plan = dict(request.narrative_plan)
        plan["narrative_structure"] = build_synced_narrative_structure(plan)
        path = store.artifact_path(job_id, "state/narrative_plan.json")
        write_json(path, plan)
        store.record_artifact(job, "narrative_plan", "state/narrative_plan.json")
        store.mark_draft_changed(job, "outline")
        return {
            "job": _get_owned_job_or_404(job_id, http_request),
            "narrative_plan": plan,
            "narrative_structure": plan["narrative_structure"],
            "issues": narrative_structure_issues(plan),
        }
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise _internal_operation_error("narrative_structure_sync", job_id, exc) from exc


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _asset_review_label_maps(job_dir: Path) -> tuple[dict[str, str], dict[str, str]]:
    narrative_plan = _read_json_file(job_dir / "state" / "narrative_plan.json")
    character_labels: dict[str, str] = {}
    for character in narrative_plan.get("characters", []):
        if not isinstance(character, dict):
            continue
        character_id = str(character.get("id", "")).strip()
        character_name = str(character.get("name", "")).strip()
        if not character_name:
            continue
        for key in {character_id, character_name, character_id.replace("_", ""), character_name.replace(" ", "")}:
            if key:
                character_labels[key.lower()] = character_name

    scene_plan = _read_json_file(job_dir / "state" / "scene_plan.json")
    if not scene_plan and narrative_plan:
        try:
            scene_plan = build_scene_plan(narrative_plan)
        except Exception:
            scene_plan = {}

    scene_labels: dict[str, str] = {}
    for scene in scene_plan.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        scene_file = str(scene.get("scene_file", "")).strip()
        title = str(scene.get("node_name") or scene.get("source_node") or "").strip()
        if scene_file and title:
            scene_labels[scene_file] = title
    for ending in scene_plan.get("endings", []):
        if not isinstance(ending, dict):
            continue
        scene_file = str(ending.get("scene_file", "")).strip()
        ending_type = str(ending.get("ending_type") or ending.get("description") or "").strip()
        if scene_file and ending_type:
            scene_labels[scene_file] = f"\u7ed3\u5c40\uff1a{ending_type}"
    return character_labels, scene_labels


def _scene_music_review(job_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    narrative_plan = _read_json_file(job_dir / "state" / "narrative_plan.json")
    scene_plan = _read_json_file(job_dir / "state" / "scene_plan.json")
    if not scene_plan and narrative_plan:
        scene_plan = build_scene_plan(narrative_plan)
    overrides_payload = _read_json_file(job_dir / "state" / "scene_music_overrides.json")
    overrides = overrides_payload.get("scene_overrides", {})
    overrides = overrides if isinstance(overrides, dict) else {}
    bgm_assets = pipeline._load_bgm_assets(job_dir)
    music_assets = sorted({asset for group in bgm_assets.values() for asset in group}, key=str.lower)
    script_lines = [
        *[f"Scene:{item.get('scene_file', '')}" for item in scene_plan.get("scenes", []) if isinstance(item, dict)],
        *[f"Ending:{item.get('scene_file', '')}" for item in scene_plan.get("endings", []) if isinstance(item, dict)],
    ]
    plan = pipeline._build_bgm_plan("\n".join(script_lines), bgm_assets, scene_plan, overrides)
    planned_by_scene = {str(item.get("scene_file", "")): item for item in plan}
    entries: list[dict[str, Any]] = []
    for collection, kind in ((scene_plan.get("scenes", []), "scene"), (scene_plan.get("endings", []), "ending")):
        for item in collection:
            if not isinstance(item, dict):
                continue
            scene_file = str(item.get("scene_file", "")).strip()
            if not scene_file:
                continue
            planned = planned_by_scene.get(scene_file, {})
            label = str(item.get("node_name") or item.get("ending_type") or item.get("source_node") or scene_file).strip()
            selected_asset = str(overrides.get(scene_file, "")).strip() or None
            entries.append({
                "scene_file": scene_file,
                "label": label,
                "kind": kind,
                "system_asset": planned.get("system_asset") or planned.get("asset") or None,
                "selected_asset": selected_asset,
                "active_asset": planned.get("asset") or None,
            })
    return entries, music_assets


def _particle_effect_review(job_id: str, job_dir: Path) -> dict[str, Any]:
    scene_music, _ = _scene_music_review(job_dir)
    state = load_particle_effect_state(job_dir)
    assignments = state["scene_effects"]
    effects = available_effects(job_dir)
    effect_items: list[dict[str, Any]] = []
    for effect_id, effect in effects.items():
        asset = str(effect.get("asset") or "")
        draft_asset = job_dir / "draft" / "game" / "tex" / "effects" / asset
        if effect_id in EFFECT_PRESETS:
            preview_url = _public_app_path(f"/play/effect-library/{asset}")
        else:
            preview_url = _public_app_path(f"/play/{job_id}/draft-game/tex/effects/{asset}")
        effect_items.append({**effect, "preview_url": _versioned_file_url(preview_url, draft_asset) if draft_asset.exists() else preview_url})
    return {
        "effects": effect_items,
        "scenes": [
            {
                "scene_file": item["scene_file"],
                "label": item["label"],
                "kind": item["kind"],
                "assignment": assignments.get(item["scene_file"]),
            }
            for item in scene_music
        ],
    }


def _character_display_name(filename: str, character_labels: dict[str, str]) -> str | None:
    stem = filename.removesuffix(".webp").removeprefix("figure_")
    parts = stem.split("_")
    candidates = {stem, stem.replace("_", "")}
    candidates.update("_".join(parts[index:]) for index in range(len(parts)))
    for candidate in candidates:
        label = character_labels.get(candidate.lower())
        if label:
            return label
    for key, label in character_labels.items():
        if key and (key in stem.lower() or stem.lower() in key):
            return label
    return None


def _fallback_asset_name(filename: str) -> str:
    return filename.removesuffix(".webp").removeprefix("figure_").removeprefix("bg_").removeprefix("title_").replace("_", " ")


def _versioned_file_url(url: str, path: Path) -> str:
    try:
        version = path.stat().st_mtime_ns
    except FileNotFoundError:
        return url
    return f"{url}?v={version}"


def _asset_review_item(
    job_id: str,
    job_dir: Path,
    image: dict[str, Any],
    character_labels: dict[str, str],
    scene_labels: dict[str, str],
) -> dict[str, Any]:
    filename = str(image.get("filename", "")).removesuffix(".webp")
    subdir = str(image.get("subdir", "")).strip()
    asset_relative = f"{subdir}/{filename}.webp"
    draft_asset_path = job_dir / "draft" / "game" / asset_relative
    asset_path = draft_asset_path if draft_asset_path.exists() else job_dir / "public" / "game" / asset_relative
    asset_url_kind = "draft-game" if draft_asset_path.exists() else "game"
    kind = "\u89d2\u8272\u7acb\u7ed8" if subdir == "figure" or filename.startswith("figure_") else "\u573a\u666f\u80cc\u666f"
    available_scene = str(image.get("available_scene", "")).strip()
    scene_display_name = scene_labels.get(available_scene, "")
    display_name = _character_display_name(filename, character_labels) if kind == "\u89d2\u8272\u7acb\u7ed8" else scene_display_name
    if not display_name:
        display_name = _fallback_asset_name(filename)

    avatar_url = None
    avatar_exists = False
    if kind == "\u89d2\u8272\u7acb\u7ed8":
        avatar_name = f"miniavatar_{filename.removeprefix('figure_')}.webp"
        avatar_relative = f"figure/{avatar_name}"
        draft_avatar_path = job_dir / "draft" / "game" / avatar_relative
        avatar_path = draft_avatar_path if draft_avatar_path.exists() else job_dir / "public" / "game" / avatar_relative
        avatar_url_kind = "draft-game" if draft_avatar_path.exists() else "game"
        avatar_exists = avatar_path.exists()
        avatar_url = _versioned_file_url(
            _public_app_path(f"/play/{job_id}/{avatar_url_kind}/{avatar_relative}"),
            avatar_path,
        )
    asset_url = _versioned_file_url(
        _public_app_path(f"/play/{job_id}/{asset_url_kind}/{asset_relative}"),
        asset_path,
    )
    crop_source_url = asset_url
    uploaded = next((item for item in _uploaded_assets(job_dir) if str(item.get("replaces_filename") or "") == filename), None)
    if uploaded and uploaded.get("oss_url"):
        asset_url = str(uploaded["oss_url"])
    return {
        "filename": filename,
        "subdir": subdir,
        "kind": kind,
        "display_name": display_name,
        "size": image.get("size", ""),
        "prompt": image.get("prompt", ""),
        "available_scene": available_scene,
        "scene_display_name": scene_display_name,
        "exists": asset_path.exists(),
        "url": asset_url,
        "crop_source_url": crop_source_url,
        "avatar_exists": avatar_exists,
        "avatar_url": avatar_url,
    }


def _uploaded_assets(job_dir: Path) -> list[dict[str, Any]]:
    payload = _read_json_file(job_dir / "state" / "uploaded_assets.json")
    items = payload.get("items", []) if isinstance(payload, dict) else []
    return [item for item in items if isinstance(item, dict)]


def _write_figure_avatar(image: Any, figure_dir: Path, figure_filename: str) -> Path:
    """Keep the dialogue avatar synchronized whenever a figure is replaced."""
    from PIL import Image
    width, height = image.size
    crop_height = max(1, int(height * 0.40))
    upper = image.crop((0, 0, width, crop_height))
    ratio = 400 / max(width, crop_height)
    resized = upper.resize((max(1, int(width * ratio)), max(1, int(crop_height * ratio))), Image.Resampling.LANCZOS)
    avatar = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    avatar.alpha_composite(resized, ((400 - resized.width) // 2, (400 - resized.height) // 2))
    stem = Path(figure_filename).stem
    avatar_name = f"miniavatar_{stem.removeprefix('figure_')}.webp" if stem.startswith("figure_") else f"miniavatar_{stem}.webp"
    avatar_path = figure_dir / avatar_name
    avatar.save(avatar_path, "WEBP", lossless=True)
    return avatar_path


def _job_music_assets(job_dir: Path) -> list[str]:
    names = {asset for group in pipeline._load_bgm_assets(job_dir).values() for asset in group}
    for root in (job_dir / "draft" / "game" / "bgm", job_dir / "public" / "game" / "bgm"):
        if root.exists(): names.update(path.name for path in root.iterdir() if path.is_file())
    return sorted(names, key=str.lower)


def _uploaded_image_review_items(job_id: str, job_dir: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in _uploaded_assets(job_dir):
        if item.get("type") != "image" or item.get("replaces_filename"): continue
        subdir, filename = str(item.get("subdir") or "background"), str(item.get("filename") or "")
        if subdir not in {"figure", "background"} or not filename: continue
        draft_path = job_dir / "draft" / "game" / subdir / filename
        public_path = job_dir / "public" / "game" / subdir / filename
        path = draft_path if draft_path.exists() else public_path
        asset_kind = "draft-game" if draft_path.exists() else "game"
        stem = Path(filename).stem
        avatar_name = f"miniavatar_{stem.removeprefix('figure_')}.webp" if stem.startswith("figure_") else f"miniavatar_{stem}.webp"
        draft_avatar = job_dir / "draft" / "game" / "figure" / avatar_name
        public_avatar = job_dir / "public" / "game" / "figure" / avatar_name
        avatar_path = draft_avatar if draft_avatar.exists() else public_avatar
        avatar_kind = "draft-game" if draft_avatar.exists() else "game"
        avatar_url = str(item.get("avatar_oss_url") or _versioned_file_url(_public_app_path(f"/play/{job_id}/{avatar_kind}/figure/{avatar_name}"), avatar_path)) if subdir == "figure" and avatar_path.exists() else None
        local_url = _versioned_file_url(_public_app_path(f"/play/{job_id}/{asset_kind}/{subdir}/{filename}"), path)
        result.append({"filename": stem, "subdir": subdir, "kind": "角色立绘" if subdir == "figure" else "场景背景", "display_name": str(item.get("display_name") or stem), "size": str(item.get("size") or "用户上传"), "prompt": "用户上传素材", "available_scene": "", "scene_display_name": "", "exists": path.exists(), "url": str(item.get("oss_url") or local_url), "crop_source_url": local_url, "avatar_exists": bool(avatar_url), "avatar_url": avatar_url, "uploaded": True})
    return result


def _tts_voice_review_payload(job_id: str, job_dir: Path, voice_enabled: bool) -> dict[str, Any]:
    review_path = job_dir / "state" / "tts_voice_review.json"
    if not voice_enabled or not review_path.exists():
        return {
            "voice_enabled": voice_enabled,
            "voices": [],
            "available_voices": [],
        }
    review = _read_json_file(review_path)
    characters: list[dict[str, Any]] = []
    for raw_item in review.get("characters", []):
        if not isinstance(raw_item, dict):
            continue
        item = dict(raw_item)
        filename = str(item.get("filename") or "").replace("\\", "/").split("/")[-1]
        preview_path = job_dir / "public" / "game" / "vocal_preview" / filename
        item["preview_exists"] = bool(filename) and preview_path.exists()
        item["preview_url"] = (
            _versioned_file_url(_public_app_path(f"/play/{job_id}/game/vocal_preview/{filename}"), preview_path)
            if item["preview_exists"]
            else None
        )
        characters.append(item)
    return {
        "voice_enabled": True,
        "voices": characters,
        "available_voices": review.get("available_voices", []),
    }


@app.get("/jobs/{job_id}/assets/review")
def get_asset_review(job_id: str, request: Request) -> dict[str, Any]:
    job = _get_owned_job_or_404(job_id, request)
    job_dir = _job_dir_or_404(job_id)
    voice_enabled = bool(job.get("options", {}).get("generate_tts", job.get("options", {}).get("voice_enabled", False)))
    voice_review = _tts_voice_review_payload(job_id, job_dir, voice_enabled)
    particle_effects = _particle_effect_review(job_id, job_dir)
    manifest_path = job_dir / "assets_manifest.json"
    if not manifest_path.exists():
        scene_music, music_assets = _scene_music_review(job_dir)
        return {
            "job": job,
            "assets": _uploaded_image_review_items(job_id, job_dir),
            "image_enabled": bool(job.get("options", {}).get("generate_assets", False)),
            "scene_music": scene_music,
            "music_assets": _job_music_assets(job_dir),
            "particle_effects": particle_effects,
            **voice_review,
        }
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"invalid assets_manifest.json: {exc}") from exc
    images = manifest.get("images", [])
    if not isinstance(images, list):
        raise HTTPException(status_code=422, detail="assets_manifest.json images must be an array")
    character_labels, scene_labels = _asset_review_label_maps(job_dir)
    scene_music, music_assets = _scene_music_review(job_dir)
    return {
        "job": job,
        "assets": [*_uploaded_image_review_items(job_id, job_dir), *[_asset_review_item(job_id, job_dir, image, character_labels, scene_labels) for image in images if isinstance(image, dict)]],
        "image_enabled": bool(job.get("options", {}).get("generate_assets", False)),
        "scene_music": scene_music,
        "music_assets": _job_music_assets(job_dir),
        "particle_effects": particle_effects,
        **voice_review,
    }


@app.post("/jobs/{job_id}/assets/upload")
async def upload_asset(job_id: str, request: Request, file: UploadFile = File(...), asset_type: str = Form(...), image_role: str = Form("background"), remove_background: bool = Form(False), replace_filename: str | None = Form(None), base_revision: int | None = Form(None)) -> dict[str, Any]:
    """Store a user asset in this job's draft; it is published only via Apply changes."""
    job = _get_owned_job_or_404(job_id, request)
    _require_job_editable(job, base_revision)
    asset_type, suffix = asset_type.strip().lower(), Path(file.filename or "").suffix.lower()
    image_suffixes, audio_suffixes = {".png", ".jpg", ".jpeg", ".webp"}, {".mp3", ".wav", ".ogg"}
    if asset_type not in {"image", "bgm"} or (asset_type == "image" and suffix not in image_suffixes) or (asset_type == "bgm" and suffix not in audio_suffixes): raise HTTPException(status_code=422, detail="unsupported file type")
    content = await file.read()
    if not content or len(content) > 30 * 1024 * 1024: raise HTTPException(status_code=422, detail="file must be between 1 byte and 30 MB")
    job_dir = _job_dir_or_404(job_id)
    safe_stem = re.sub(r"[^a-zA-Z0-9_-]+", "_", Path(file.filename or "upload").stem).strip("_") or "upload"
    if asset_type == "image":
        from io import BytesIO
        from PIL import Image
        try:
            image = Image.open(BytesIO(content)); image.verify(); image = Image.open(BytesIO(content)).convert("RGBA")
        except Exception as exc: raise HTTPException(status_code=422, detail="invalid image file") from exc
        if remove_background:
            try:
                from rembg import remove
                image = remove(image)
            except Exception as exc: raise HTTPException(status_code=503, detail="background removal is temporarily unavailable") from exc
        subdir = "figure" if image_role == "figure" else "background"
        replacement_stem = Path(replace_filename or "").name.removesuffix(".webp")
        if replace_filename and replacement_stem != replace_filename.removesuffix(".webp"):
            raise HTTPException(status_code=422, detail="invalid replacement filename")
        stored_name = f"{replacement_stem}.webp" if replacement_stem else f"upload_{uuid.uuid4().hex[:10]}_{safe_stem}.webp"
        target = job_dir / "draft" / "game" / subdir / stored_name; target.parent.mkdir(parents=True, exist_ok=True); image.save(target, "WEBP", lossless=True)
        avatar_path = _write_figure_avatar(image, target.parent, stored_name) if subdir == "figure" else None
        item: dict[str, Any] = {"type": "image", "subdir": subdir, "filename": stored_name, "display_name": safe_stem, "size": f"{image.width}×{image.height}", "status": "staged"}
        existing_standalone = next((existing for existing in _uploaded_assets(job_dir) if existing.get("type") == "image" and not existing.get("replaces_filename") and Path(str(existing.get("filename") or "")).stem == replacement_stem), None)
        if replacement_stem and not existing_standalone: item["replaces_filename"] = replacement_stem
    else:
        stored_name = f"upload_{uuid.uuid4().hex[:10]}_{safe_stem}{suffix}"; target = job_dir / "draft" / "game" / "bgm" / stored_name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(content)
        item = {"type": "bgm", "filename": stored_name, "display_name": safe_stem, "content_type": file.content_type, "status": "staged"}
    if settings.asset_library_enabled:
        user = _require_sso_user(request)
        logical_subdir = subdir if asset_type == "image" else "bgm"
        try:
            record = asset_library.register_file(
                user_id=str(user["id"]), job_id=job_id, source_type="UPLOADED",
                kind="FIGURE" if logical_subdir == "figure" else "BACKGROUND" if logical_subdir == "background" else "BGM",
                source_key=f"{logical_subdir}/{stored_name}", display_name=safe_stem, path=target,
                generation_metadata={"schema_version": 1, "original_filename": file.filename},
            )
            item.update({"asset_id": record.asset_id, "asset_file_id": record.file_id, "oss_key": record.object_key, "oss_url": record.url, "status": "published"})
            if asset_type == "image" and avatar_path:
                avatar = asset_library.register_file(
                    user_id=str(user["id"]), job_id=job_id, source_type="UPLOADED", kind="FIGURE",
                    source_key=f"{logical_subdir}/{stored_name}", display_name=safe_stem, path=avatar_path,
                    variant="avatar", generation_metadata={"schema_version": 1, "original_filename": file.filename},
                )
                item.update({"avatar_asset_file_id": avatar.file_id, "avatar_oss_key": avatar.object_key, "avatar_oss_url": avatar.url})
        except (AssetLibraryError, FileNotFoundError) as exc:
            raise _asset_library_http_error(exc) from exc
    items = _uploaded_assets(job_dir)
    items = [existing for existing in items if not (existing.get("type") == item.get("type") and existing.get("subdir") == item.get("subdir") and existing.get("filename") == item.get("filename"))]
    items.append(item); write_json(job_dir / "state" / "uploaded_assets.json", {"version": 1, "items": items})
    store.record_artifact(job, "uploaded_assets", "state/uploaded_assets.json"); store.mark_draft_changed(job, "assets" if asset_type == "image" else "music")
    return {"job": _get_owned_job_or_404(job_id, request), "asset": item}


@app.post("/jobs/{job_id}/assets/remove-background")
def remove_asset_background(job_id: str, payload: AssetRemoveBackgroundRequest, request: Request) -> dict[str, Any]:
    job = _get_owned_job_or_404(job_id, request)
    _require_job_editable(job, payload.base_revision)
    filename = Path(payload.filename).name.removesuffix(".webp")
    if filename != payload.filename.removesuffix(".webp"):
        raise HTTPException(status_code=422, detail="invalid asset filename")
    job_dir = _job_dir_or_404(job_id)
    relative = Path("figure") / f"{filename}.webp"
    source = job_dir / "draft" / "game" / relative
    if not source.exists(): source = job_dir / "public" / "game" / relative
    if not source.exists(): raise HTTPException(status_code=404, detail="figure asset not found")
    try:
        from PIL import Image
        from rembg import remove
        output = remove(Image.open(source).convert("RGBA"))
        target = job_dir / "draft" / "game" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        output.save(target, "WEBP", lossless=True)
        avatar_path = _write_figure_avatar(output, target.parent, target.name)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="background removal is temporarily unavailable") from exc
    upload_record = next((item for item in _uploaded_assets(job_dir) if item.get("type") == "image" and Path(str(item.get("filename") or "")).stem == filename), None)
    upload_record = dict(upload_record) if upload_record else {"type": "image", "subdir": "figure", "filename": f"{filename}.webp", "display_name": filename, "replaces_filename": filename}
    for key in ("oss_key", "oss_url", "avatar_oss_key", "avatar_oss_url"):
        upload_record.pop(key, None)
    upload_record["status"] = "staged"
    if settings.asset_library_enabled:
        user = _require_sso_user(request)
        try:
            original = asset_library.register_file(
                user_id=str(user["id"]), job_id=job_id, source_type="UPLOADED", kind="FIGURE",
                source_key=f"figure/{target.name}", display_name=str(upload_record["display_name"]), path=target,
                generation_metadata={"schema_version": 1, "operation": "remove_background"},
            )
            avatar_file = asset_library.register_file(
                user_id=str(user["id"]), job_id=job_id, source_type="UPLOADED", kind="FIGURE",
                source_key=f"figure/{target.name}", display_name=str(upload_record["display_name"]), path=avatar_path,
                variant="avatar", generation_metadata={"schema_version": 1, "operation": "remove_background"},
            )
            upload_record.update({"asset_id": original.asset_id, "asset_file_id": original.file_id, "oss_key": original.object_key, "oss_url": original.url, "avatar_asset_file_id": avatar_file.file_id, "avatar_oss_key": avatar_file.object_key, "avatar_oss_url": avatar_file.url, "status": "published"})
        except (AssetLibraryError, FileNotFoundError) as exc:
            raise _asset_library_http_error(exc) from exc
    items = [item for item in _uploaded_assets(job_dir) if not (item.get("type") == "image" and Path(str(item.get("filename") or "")).stem == filename)]
    items.append(upload_record)
    write_json(job_dir / "state" / "uploaded_assets.json", {"version": 1, "items": items})
    store.mark_draft_changed(job, "assets")
    return {"job": _get_owned_job_or_404(job_id, request), "filename": filename}


@app.post("/jobs/{job_id}/assets/avatar-crop")
def crop_asset_avatar(job_id: str, payload: AvatarCropRequest, request: Request) -> dict[str, Any]:
    job = _get_owned_job_or_404(job_id, request)
    _require_job_editable(job, payload.base_revision)
    filename = Path(payload.filename).name.removesuffix(".webp")
    if filename != payload.filename.removesuffix(".webp"):
        raise HTTPException(status_code=422, detail="invalid asset filename")
    job_dir = _job_dir_or_404(job_id)
    relative = Path("figure") / f"{filename}.webp"
    source = job_dir / "draft" / "game" / relative
    if not source.exists(): source = job_dir / "public" / "game" / relative
    if not source.exists(): raise HTTPException(status_code=404, detail="figure asset not found")
    try:
        from PIL import Image
        image = Image.open(source).convert("RGBA")
        base_scale = max(400 / image.width, 400 / image.height)
        scale = base_scale * payload.zoom
        resized = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.LANCZOS)
        avatar = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
        x = round((400 - resized.width) / 2 + payload.offset_x * 400)
        y = round((400 - resized.height) / 2 + payload.offset_y * 400)
        avatar.alpha_composite(resized, (x, y))
        avatar_name = f"miniavatar_{filename.removeprefix('figure_')}.webp" if filename.startswith("figure_") else f"miniavatar_{filename}.webp"
        target = job_dir / "draft" / "game" / "figure" / avatar_name
        target.parent.mkdir(parents=True, exist_ok=True)
        avatar.save(target, "WEBP", lossless=True)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="avatar crop failed") from exc
    record = next((dict(item) for item in _uploaded_assets(job_dir) if item.get("type") == "image" and Path(str(item.get("filename") or "")).stem == filename), None)
    record = record or {"type": "image", "subdir": "figure", "filename": f"{filename}.webp", "display_name": filename, "replaces_filename": filename}
    for key in ("oss_key", "oss_url", "avatar_oss_key", "avatar_oss_url"):
        record.pop(key, None)
    record["status"] = "staged"
    if settings.asset_library_enabled:
        user = _require_sso_user(request)
        try:
            avatar_file = asset_library.register_file(
                user_id=str(user["id"]), job_id=job_id, source_type="UPLOADED", kind="FIGURE",
                source_key=f"figure/{filename}.webp", display_name=str(record["display_name"]), path=target,
                variant="avatar", generation_metadata={"schema_version": 1, "operation": "avatar_crop"},
            )
            record.update({"asset_id": avatar_file.asset_id, "avatar_asset_file_id": avatar_file.file_id, "avatar_oss_key": avatar_file.object_key, "avatar_oss_url": avatar_file.url, "status": "published"})
        except (AssetLibraryError, FileNotFoundError) as exc:
            raise _asset_library_http_error(exc) from exc
    items = [item for item in _uploaded_assets(job_dir) if not (item.get("type") == "image" and Path(str(item.get("filename") or "")).stem == filename)]
    items.append(record)
    write_json(job_dir / "state" / "uploaded_assets.json", {"version": 1, "items": items})
    store.mark_draft_changed(job, "assets")
    return {"job": _get_owned_job_or_404(job_id, request), "filename": filename}


@app.put("/jobs/{job_id}/scene-music")
def update_scene_music(job_id: str, request: SceneMusicOverrideRequest, http_request: Request) -> dict[str, Any]:
    job = _get_owned_job_or_404(job_id, http_request)
    if job.get("options", {}).get("generation_mode", "advanced") != "advanced":
        raise HTTPException(status_code=403, detail="scene music selection is available in advanced mode only")
    _require_job_editable(job, request.base_revision)
    job_dir = _job_dir_or_404(job_id)
    scene_music, music_assets = _scene_music_review(job_dir)
    music_assets = _job_music_assets(job_dir)
    valid_scenes = {str(item["scene_file"]) for item in scene_music}
    scene_file = request.scene_file.replace("\\", "/").split("/")[-1]
    if scene_file not in valid_scenes:
        raise HTTPException(status_code=422, detail="unknown scene file")
    asset = (request.asset or "").strip()
    if asset and asset not in set(music_assets):
        raise HTTPException(status_code=422, detail="music asset is not available in the library")
    path = job_dir / "state" / "scene_music_overrides.json"
    payload = _read_json_file(path)
    if job.get("has_published_build"):
        published_snapshot = job_dir / "state" / "published_scene_music_overrides.json"
        if not published_snapshot.exists():
            write_json(published_snapshot, payload if payload else {"version": 1, "scene_overrides": {}})
    overrides = payload.get("scene_overrides", {})
    overrides = dict(overrides) if isinstance(overrides, dict) else {}
    if asset:
        overrides[scene_file] = asset
    else:
        overrides.pop(scene_file, None)
    write_json(path, {"version": 1, "scene_overrides": overrides})
    store.record_artifact(job, "scene_music_overrides", "state/scene_music_overrides.json")
    store.mark_draft_changed(job, "music")
    return {"job": _get_owned_job_or_404(job_id, http_request), "scene_file": scene_file, "asset": asset or None}


@app.put("/jobs/{job_id}/scene-presentation-draft")
def update_scene_presentation_draft(
    job_id: str,
    request: ScenePresentationDraftRequest,
    http_request: Request,
) -> dict[str, Any]:
    """Persist all locally staged scene music/effect edits in one revision."""
    job = _get_owned_job_or_404(job_id, http_request)
    if job.get("options", {}).get("generation_mode", "advanced") != "advanced":
        raise HTTPException(status_code=403, detail="scene presentation editing is available in advanced mode only")
    _require_job_editable(job, request.base_revision)
    job_dir = _job_dir_or_404(job_id)
    scene_music, music_assets = _scene_music_review(job_dir)
    music_assets = _job_music_assets(job_dir)
    valid_scenes = {str(item["scene_file"]) for item in scene_music}
    normalized_music = {Path(scene.replace("\\", "/")).name: (asset or "").strip() for scene, asset in request.music.items()}
    normalized_effects = {Path(scene.replace("\\", "/")).name: raw for scene, raw in request.effects.items()}
    if any(scene not in valid_scenes for scene in [*normalized_music, *normalized_effects]):
        raise HTTPException(status_code=422, detail="unknown scene file")
    if any(asset and asset not in set(music_assets) for asset in normalized_music.values()):
        raise HTTPException(status_code=422, detail="music asset is not available in the library")
    for raw in normalized_effects.values():
        if raw:
            try:
                normalize_assignment(raw, available_effects(job_dir))
            except ParticleEffectError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
    if job.get("has_published_build"):
        for path, fallback in (
            (job_dir / "state" / "published_scene_music_overrides.json", {"version": 1, "scene_overrides": {}}),
            (job_dir / "state" / "published_particle_effects.json", {"version": 1, "scene_effects": {}}),
        ):
            if not path.exists():
                source = _read_json_file(job_dir / "state" / path.name.removeprefix("published_"))
                write_json(path, source if source else fallback)
    if normalized_music:
        path = job_dir / "state" / "scene_music_overrides.json"
        payload = _read_json_file(path)
        overrides = dict(payload.get("scene_overrides", {})) if isinstance(payload.get("scene_overrides"), dict) else {}
        for scene, asset in normalized_music.items():
            if asset: overrides[scene] = asset
            else: overrides.pop(scene, None)
        write_json(path, {"version": 1, "scene_overrides": overrides})
        store.record_artifact(job, "scene_music_overrides", "state/scene_music_overrides.json")
    for scene, raw in normalized_effects.items():
        try:
            save_scene_assignment(job_dir, scene, raw)
        except ParticleEffectError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    if normalized_effects:
        store.record_artifact(job, "particle_effects", "state/particle_effects.json")
    if normalized_music: store.mark_draft_changed(job, "music")
    if normalized_effects: store.mark_draft_changed(job, "effects")
    return {"job": _get_owned_job_or_404(job_id, http_request)}


@app.get("/jobs/{job_id}/music-library/{asset_name}")
def preview_music_library_asset(job_id: str, asset_name: str, request: Request) -> FileResponse:
    _get_owned_job_or_404(job_id, request)
    clean_name = Path(asset_name).name
    if clean_name != asset_name or clean_name.startswith("."):
        raise HTTPException(status_code=404, detail="music asset not found")
    job_dir = _job_dir_or_404(job_id)
    available_assets = set(_job_music_assets(job_dir))
    if clean_name not in available_assets:
        raise HTTPException(status_code=404, detail="music asset not found")
    for path in (job_dir / "draft" / "game" / "bgm" / clean_name, job_dir / "public" / "game" / "bgm" / clean_name):
        if path.exists(): return FileResponse(path)
    return _file_response_under_root(root=settings.sound_effects_dir, file_path=clean_name, missing_detail="music asset not found")


@app.get("/effect-library/{asset_name}")
@app.get("/play/effect-library/{asset_name}")
def preview_particle_effect_asset(asset_name: str) -> FileResponse:
    clean_name = Path(asset_name).name
    allowed = {str(item["asset"]) for item in EFFECT_PRESETS.values()}
    if clean_name != asset_name or clean_name not in allowed:
        raise HTTPException(status_code=404, detail="particle effect asset not found")
    return _file_response_under_root(
        root=settings.workspace_root / "public" / "game" / "tex" / "effects",
        file_path=clean_name,
        missing_detail="particle effect asset not found",
    )


@app.put("/jobs/{job_id}/scene-effect")
def update_scene_effect(job_id: str, request: SceneEffectRequest, http_request: Request) -> dict[str, Any]:
    job = _get_owned_job_or_404(job_id, http_request)
    if job.get("options", {}).get("generation_mode", "advanced") != "advanced":
        raise HTTPException(status_code=403, detail="scene effect editing is available in advanced mode only")
    _require_job_editable(job, request.base_revision)
    job_dir = _job_dir_or_404(job_id)
    valid_scenes = {str(item["scene_file"]) for item in _particle_effect_review(job_id, job_dir)["scenes"]}
    scene_file = Path(request.scene_file.replace("\\", "/")).name
    if scene_file not in valid_scenes:
        raise HTTPException(status_code=422, detail="unknown scene file")
    payload = request.model_dump(exclude={"scene_file", "base_revision"}, exclude_none=True)
    try:
        assignment = save_scene_assignment(job_dir, scene_file, payload)
    except ParticleEffectError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    store.record_artifact(job, "particle_effects", "state/particle_effects.json")
    store.mark_draft_changed(job, "effects")
    return {
        "job": _get_owned_job_or_404(job_id, http_request),
        "scene_file": scene_file,
        "assignment": assignment or None,
        "particle_effects": _particle_effect_review(job_id, job_dir),
    }


@app.post("/jobs/{job_id}/voices/preview")
def regenerate_voice_preview(job_id: str, request: TTSPreviewRequest, http_request: Request) -> dict[str, Any]:
    try:
        job = _get_owned_job_or_404(job_id, http_request)
        item = pipeline.regenerate_tts_preview(job, request.speaker.strip(), request.voice.strip())
        return {
            "job": _get_owned_job_or_404(job_id, http_request),
            "voice": item,
            **_tts_voice_review_payload(job_id, store.job_dir(job_id), True),
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PipelineError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/jobs/{job_id}/assets/regenerate")
def regenerate_asset(
    job_id: str,
    request: AssetRegenerateRequest,
    background_tasks: BackgroundTasks,
    http_request: Request,
) -> dict[str, Any]:
    filename = request.filename.replace("\\", "/").split("/")[-1].removesuffix(".webp")
    if not filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="invalid asset filename")
    if request.background:
        job = _get_owned_job_or_404(job_id, http_request)
        _require_job_editable(job, request.base_revision)
        background_tasks.add_task(run_asset_regeneration_background, job_id, filename, request.prompt)
        store.transition(job, "QUEUED", "ASSET_GENERATION")
        return {"job": job, "queued": True, "filename": filename}
    try:
        job = _get_owned_job_or_404(job_id, http_request)
        _require_job_editable(job, request.base_revision)
        image = pipeline.regenerate_asset_image(job, filename, request.prompt)
        return {"job": _get_owned_job_or_404(job_id, http_request), "queued": False, "asset": image}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PipelineError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/jobs/{job_id}/run")
def run_job(job_id: str, request: RunJobRequest, background_tasks: BackgroundTasks, http_request: Request) -> dict[str, Any]:
    current_job = _get_owned_job_or_404(job_id, http_request)
    if current_job.get("status") in {"RUNNING", "QUEUED"}:
        raise HTTPException(status_code=409, detail="job is already running")
    if request.background:
        job = _get_owned_job_or_404(job_id, http_request)
        background_tasks.add_task(run_pipeline_background, job_id)
        store.transition(job, "QUEUED", job.get("phase"))
        return job
    try:
        return pipeline.run_all(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PipelineError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/jobs/{job_id}/apply-draft")
def apply_draft(
    job_id: str,
    request: RunJobRequest,
    background_tasks: BackgroundTasks,
    http_request: Request,
) -> dict[str, Any]:
    job = _get_owned_job_or_404(job_id, http_request)
    if job.get("status") in {"RUNNING", "QUEUED"}:
        raise HTTPException(status_code=409, detail="job is already running")
    if not job.get("has_published_build"):
        raise HTTPException(status_code=409, detail="game must be built before draft changes can be applied")
    if request.background:
        background_tasks.add_task(run_apply_draft_background, job_id)
        store.transition(job, "QUEUED", "DRAFT_APPLY")
        return job
    try:
        pipeline.apply_draft_changes(job)
        return store.get(job_id)
    except PipelineError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/jobs/{job_id}/phases/{phase}")
def run_phase(
    job_id: str,
    phase: str,
    background_tasks: BackgroundTasks,
    http_request: Request,
    request: RunJobRequest = RunJobRequest(),
) -> dict[str, Any]:
    if phase not in pipeline.phase_names():
        raise HTTPException(status_code=422, detail=f"unknown phase: {phase}")
    current_job = _get_owned_job_or_404(job_id, http_request)
    if current_job.get("status") in {"RUNNING", "QUEUED"}:
        raise HTTPException(status_code=409, detail="job is already running")
    if request.background:
        job = _get_owned_job_or_404(job_id, http_request)
        background_tasks.add_task(run_phase_background, job_id, phase)
        store.transition(job, "QUEUED", phase.upper())
        return job
    try:
        return pipeline.run_phase(job_id, phase)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PipelineError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/jobs/{job_id}/artifacts")
def list_artifacts(job_id: str, request: Request) -> dict[str, Any]:
    _get_owned_job_or_404(job_id, request)
    try:
        return {"job_id": job_id, "artifacts": store.list_artifacts(job_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/jobs/{job_id}/artifacts/{artifact_path:path}")
def get_artifact(job_id: str, artifact_path: str, request: Request) -> FileResponse:
    if contains_hidden_path(artifact_path):
        raise HTTPException(status_code=404, detail="artifact not found")
    _get_owned_job_or_404(job_id, request)
    try:
        path = store.artifact_path(job_id, artifact_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"artifact not found: {artifact_path}")
    return FileResponse(path)


@app.get("/play/{job_id}/game/{file_path:path}")
def play_game_asset(job_id: str, file_path: str) -> FileResponse:
    if contains_hidden_path(file_path):
        raise HTTPException(status_code=404, detail=f"game asset not found: {file_path}")
    job_dir = _job_dir_or_404(job_id)
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    backup_root = job_dir / "state" / "published_game_backup"
    game_root = backup_root if store.get(job_id).get("build_state") == "BUILDING" and backup_root.exists() else job_dir / "public" / "game"
    return _file_response_under_root(
        root=game_root,
        file_path=file_path,
        missing_detail=f"game asset not found: {file_path}",
    )


@app.get("/play/{job_id}/draft-game/{file_path:path}")
def play_draft_game_asset(job_id: str, file_path: str) -> FileResponse:
    if contains_hidden_path(file_path):
        raise HTTPException(status_code=404, detail=f"draft game asset not found: {file_path}")
    job_dir = _job_dir_or_404(job_id)
    return _file_response_under_root(
        root=job_dir / "draft" / "game",
        file_path=file_path,
        missing_detail=f"draft game asset not found: {file_path}",
    )


@app.get("/play/game/{file_path:path}")
def play_game_asset_from_referer(file_path: str, request: Request) -> FileResponse:
    referer = request.headers.get("referer", "")
    match = re.search(r"/play/([A-Za-z0-9_-]+)(?:/|$)", referer)
    if not match:
        raise HTTPException(status_code=404, detail=f"game asset not found: {file_path}")
    return play_game_asset(match.group(1), file_path)


@app.get("/play/{job_id}/assets/{file_path:path}")
def play_engine_asset(job_id: str, file_path: str) -> FileResponse:
    if not engine_dist_dir.exists():
        raise HTTPException(status_code=404, detail="engine not built; run npm run build first")
    return _file_response_under_root(
        root=engine_dist_dir / "assets",
        file_path=file_path,
        missing_detail=f"engine asset not found: {file_path}",
    )


@app.get("/play/{job_id}/static-engine/{file_path:path}")
def play_engine_static(job_id: str, file_path: str) -> FileResponse:
    if not engine_dist_dir.exists():
        raise HTTPException(status_code=404, detail="engine not built")
    return _file_response_under_root(
        root=engine_dist_dir,
        file_path=file_path,
        missing_detail=f"not found: {file_path}",
    )


@app.get("/play/{job_id}/index.html")
@app.get("/play/{job_id}/")
@app.get("/play/{job_id}")
def play_game_with_slash(job_id: str) -> HTMLResponse:
    job_dir = _job_dir_or_404(job_id)
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    if not engine_dist_dir.exists():
        raise HTTPException(status_code=404, detail="engine not built; run npm run build first")

    index_path = engine_dist_dir / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="engine index.html not found")

    play_root = _public_app_path(f"/play/{job_id}/")
    asset_root = _public_app_path(f"/play/{job_id}/assets/")
    game_root = _public_app_path(f"/play/{job_id}/game/")
    static_root = _public_app_path(f"/play/{job_id}/static-engine/")

    html = index_path.read_text(encoding="utf-8")
    html = html.replace("./assets/", asset_root)
    html = html.replace("./game/", game_root)
    html = html.replace("./icons/", f"{static_root}icons/")
    html = html.replace("./manifest.json", f"{static_root}manifest.json")
    html = html.replace("./webgal-serviceworker.js", f"{static_root}webgal-serviceworker.js")
    html = html.replace("loadIifePlugin('lib/", f"loadIifePlugin('{static_root}lib/")
    html = html.replace("<head>", f'<head>\n    <base href="{play_root}" />', 1)
    return HTMLResponse(content=html)


def _file_response_under_root(*, root: Path, file_path: str, missing_detail: str) -> FileResponse:
    resolved_root = root.resolve()
    path = (resolved_root / file_path).resolve()
    if resolved_root not in path.parents and resolved_root != path:
        raise HTTPException(status_code=400, detail="invalid path")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=missing_detail)
    content_type, _ = mimetypes.guess_type(str(path))
    return FileResponse(path, media_type=content_type)


def run_pipeline_background(job_id: str) -> None:
    try:
        pipeline.run_all(job_id)
    except Exception:
        logging.getLogger("uvicorn.error").exception("Forge pipeline failed for job_id=%s", job_id)


def run_apply_draft_background(job_id: str) -> None:
    try:
        pipeline.apply_draft_changes(store.get(job_id))
    except Exception as exc:
        try:
            store.set_error(store.get(job_id), str(exc))
        except Exception:
            pass
        logging.getLogger("uvicorn.error").exception("Forge draft apply failed for job_id=%s", job_id)


def run_phase_background(job_id: str, phase: str) -> None:
    try:
        job = store.get(job_id)
        advanced_mode = job.get("options", {}).get("generation_mode") == "advanced"
    except Exception:
        advanced_mode = False

    retries = settings.max_advanced_phase_retries if advanced_mode else 0
    for attempt in range(retries + 1):
        try:
            pipeline.run_phase(job_id, phase)
            return
        except PipelineError as exc:
            if attempt < retries:
                logger.warning(
                    "Retrying Advanced phase after generation failure: job_id=%s phase=%s attempt=%s/%s error=%s",
                    job_id,
                    phase,
                    attempt + 1,
                    retries,
                    exc,
                )
                # The phase runner sets FAILED on every attempt. Move it back
                # to QUEUED so polling clients do not expose a transient error.
                try:
                    store.transition(store.get(job_id), "QUEUED", phase.upper())
                except Exception:
                    logger.exception("Could not queue Advanced retry for job_id=%s phase=%s", job_id, phase)
                    return
                continue
            if retries:
                message = f"{exc}\n\nAdvanced 模式已自动重试 {retries} 次，仍未完成；你可以手动重试此阶段。"
                try:
                    store.set_error(store.get(job_id), message)
                except Exception:
                    logger.exception("Could not save exhausted retry message for job_id=%s phase=%s", job_id, phase)
            logger.exception("Forge pipeline phase failed for job_id=%s phase=%s", job_id, phase)
            return
        except Exception:
            logging.getLogger("uvicorn.error").exception("Forge pipeline phase failed for job_id=%s phase=%s", job_id, phase)
            return


def run_asset_regeneration_background(job_id: str, filename: str, prompt: str | None) -> None:
    try:
        job = store.get(job_id)
        pipeline.regenerate_asset_image(job, filename, prompt)
    except Exception as exc:
        try:
            store.set_error(store.get(job_id), str(exc))
        except Exception:
            pass
        logging.getLogger("uvicorn.error").exception("Forge asset regeneration failed for job_id=%s filename=%s", job_id, filename)


def _read_narrative_plan(job_id: str) -> dict[str, Any]:
    path = store.artifact_path(job_id, "state/narrative_plan.json")
    if not path.exists():
        raise FileNotFoundError(f"narrative plan not found for job_id={job_id}")
    return json.loads(path.read_text(encoding="utf-8"))
