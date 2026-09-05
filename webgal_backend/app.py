from __future__ import annotations

import json
import logging
import hashlib
import mimetypes
import os
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import artifacts
from .artifacts import contains_hidden_path
from .config import settings
from .job_options import GenerationOptions, normalize_generation_options
from .narrative_nodes import NarrativeNodeError, NarrativeNodeKind, generate_narrative_node as generate_narrative_node_payload
from .narrative_structure import build_synced_narrative_structure, narrative_structure_issues
from .pipeline import PipelineError, WebGALPipeline
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
INVITE_HEADER_NAME = "X-WebGAL-Invite-Code"
INVITE_CODES_ENV = "WEBGAL_INVITE_CODES"
INVITE_CODES_FILE_ENV = "WEBGAL_INVITE_CODES_FILE"


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


def _invite_hash(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def _invite_hash_from_entry(entry: str) -> str | None:
    value = entry.strip()
    if not value or value.startswith("#"):
        return None
    if value.startswith("sha256:"):
        digest = value.removeprefix("sha256:").strip().lower()
        return digest if re.fullmatch(r"[a-f0-9]{64}", digest) else None
    return _invite_hash(value)


def _configured_invite_hashes() -> tuple[set[str], bool]:
    configured = False
    hashes: set[str] = set()

    raw = os.getenv(INVITE_CODES_ENV, "").strip()
    if raw:
        configured = True
        for item in re.split(r"[\s,;]+", raw):
            digest = _invite_hash_from_entry(item)
            if digest:
                hashes.add(digest)

    file_value = os.getenv(INVITE_CODES_FILE_ENV, "").strip()
    if file_value:
        configured = True
        path = Path(file_value)
        if not path.is_absolute():
            path = (settings.workspace_root / path).resolve()
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                digest = _invite_hash_from_entry(line)
                if digest:
                    hashes.add(digest)

    return hashes, configured


def _identity_from_request(request: Request) -> dict[str, str]:
    code = unquote(request.headers.get(INVITE_HEADER_NAME) or "").strip()
    if not code:
        raise HTTPException(status_code=401, detail="invite code is required")
    invite_hash = _invite_hash(code)
    allowed, configured = _configured_invite_hashes()
    if configured and invite_hash not in allowed:
        raise HTTPException(status_code=403, detail="invalid invite code")
    return {"type": "invite", "invite_hash": invite_hash}


def _job_belongs_to_identity(job: dict[str, Any], identity: dict[str, str]) -> bool:
    stored = job.get("identity")
    if not isinstance(stored, dict):
        return False
    return stored.get("type") == identity.get("type") and stored.get("invite_hash") == identity.get("invite_hash")


def _get_owned_job_or_404(job_id: str, request: Request) -> dict[str, Any]:
    identity = _identity_from_request(request)
    job = _get_job_or_404(job_id)
    if not _job_belongs_to_identity(job, identity):
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    return job


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


class SceneMusicOverrideRequest(BaseModel):
    scene_file: str = Field(min_length=1)
    asset: str | None = None
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
    jobs = []
    for path in sorted(store.jobs_dir.glob("*/job.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            job = store.get(path.parent.name)
        except FileNotFoundError:
            continue
        if _job_belongs_to_identity(job, identity):
            jobs.append(job)
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

    try:
        if relative.endswith(".json"):
            write_json(path, json.loads(request.content))
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
    bgm_assets = pipeline._load_bgm_assets()
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
        "avatar_exists": avatar_exists,
        "avatar_url": avatar_url,
    }


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
    manifest_path = job_dir / "assets_manifest.json"
    if not manifest_path.exists():
        scene_music, music_assets = _scene_music_review(job_dir)
        return {
            "job": job,
            "assets": [],
            "image_enabled": bool(job.get("options", {}).get("generate_assets", False)),
            "scene_music": scene_music,
            "music_assets": music_assets,
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
        "assets": [_asset_review_item(job_id, job_dir, image, character_labels, scene_labels) for image in images if isinstance(image, dict)],
        "image_enabled": bool(job.get("options", {}).get("generate_assets", False)),
        "scene_music": scene_music,
        "music_assets": music_assets,
        **voice_review,
    }


@app.put("/jobs/{job_id}/scene-music")
def update_scene_music(job_id: str, request: SceneMusicOverrideRequest, http_request: Request) -> dict[str, Any]:
    job = _get_owned_job_or_404(job_id, http_request)
    if job.get("options", {}).get("generation_mode", "advanced") != "advanced":
        raise HTTPException(status_code=403, detail="scene music selection is available in advanced mode only")
    _require_job_editable(job, request.base_revision)
    job_dir = _job_dir_or_404(job_id)
    scene_music, music_assets = _scene_music_review(job_dir)
    valid_scenes = {str(item["scene_file"]) for item in scene_music}
    scene_file = request.scene_file.replace("\\", "/").split("/")[-1]
    if scene_file not in valid_scenes:
        raise HTTPException(status_code=422, detail="unknown scene file")
    asset = (request.asset or "").strip()
    if asset and asset not in set(music_assets):
        raise HTTPException(status_code=422, detail="music asset is not available in the library")
    path = job_dir / "state" / "scene_music_overrides.json"
    payload = _read_json_file(path)
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


@app.get("/jobs/{job_id}/music-library/{asset_name}")
def preview_music_library_asset(job_id: str, asset_name: str, request: Request) -> FileResponse:
    _get_owned_job_or_404(job_id, request)
    clean_name = Path(asset_name).name
    if clean_name != asset_name or clean_name.startswith("."):
        raise HTTPException(status_code=404, detail="music asset not found")
    available_assets = {asset for group in pipeline._load_bgm_assets().values() for asset in group}
    if clean_name not in available_assets:
        raise HTTPException(status_code=404, detail="music asset not found")
    return _file_response_under_root(
        root=settings.sound_effects_dir,
        file_path=clean_name,
        missing_detail="music asset not found",
    )


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
