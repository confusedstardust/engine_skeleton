from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

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


class GenerateNarrativeNodeRequest(BaseModel):
    kind: NarrativeNodeKind
    prompt: str = Field(min_length=1)
    narrative_plan: dict[str, Any] | None = None


class SyncNarrativeStructureRequest(BaseModel):
    narrative_plan: dict[str, Any]


class AssetRegenerateRequest(BaseModel):
    filename: str = Field(min_length=1)
    prompt: str | None = None
    background: bool = True


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
def create_job(request: CreateJobRequest) -> dict[str, Any]:
    return store.create(request.source_material, normalize_generation_options(request.options))


@app.get("/jobs")
def list_jobs() -> dict[str, Any]:
    jobs = []
    for path in sorted(store.jobs_dir.glob("*/job.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            jobs.append(store.get(path.parent.name))
        except FileNotFoundError:
            continue
    return {"jobs": jobs}


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    return _get_job_or_404(job_id)


@app.get("/jobs/{job_id}/nodes")
def get_job_nodes(job_id: str) -> dict[str, Any]:
    job = _get_job_or_404(job_id)
    job_dir = _job_dir_or_404(job_id)
    nodes = [artifacts.node_payload(job_dir, item) for item in artifacts.NODE_ARTIFACTS]
    return {"job": job, "nodes": nodes, "scenes": artifacts.scene_payloads(job_dir)}


@app.patch("/jobs/{job_id}/artifacts")
def update_artifact(job_id: str, request: ArtifactUpdateRequest) -> dict[str, Any]:
    if contains_hidden_path(request.path):
        raise HTTPException(status_code=404, detail="artifact not found")
    try:
        job = _get_job_or_404(job_id)
        path = store.artifact_path(job_id, request.path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    relative = artifacts.normalize_artifact_path(request.path)
    if not artifacts.is_editable_artifact(relative):
        raise HTTPException(status_code=400, detail=f"artifact is not editable: {relative}")

    try:
        if relative.endswith(".json"):
            write_json(path, json.loads(request.content))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(request.content.rstrip() + "\n", encoding="utf-8")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"invalid JSON: {exc}") from exc

    store.record_artifact(job, artifacts.artifact_key_for_path(relative), relative)
    return {"job": _get_job_or_404(job_id), "path": relative, "saved": True}


@app.post("/jobs/{job_id}/narrative-node")
def generate_narrative_node(job_id: str, request: GenerateNarrativeNodeRequest) -> dict[str, Any]:
    try:
        _get_job_or_404(job_id)
        plan = request.narrative_plan or _read_narrative_plan(job_id)
        node = generate_narrative_node_payload(
            job_dir=store.job_dir(job_id),
            llm_factory=pipeline.llm_factory,
            kind=request.kind,
            user_prompt=request.prompt,
            narrative_plan=plan,
        )
        return {"kind": request.kind, "node": node}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (NarrativeNodeError, ValueError, PipelineError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/jobs/{job_id}/narrative-structure/sync")
def sync_narrative_structure(job_id: str, request: SyncNarrativeStructureRequest) -> dict[str, Any]:
    try:
        job = _get_job_or_404(job_id)
        plan = dict(request.narrative_plan)
        plan["narrative_structure"] = build_synced_narrative_structure(plan)
        path = store.artifact_path(job_id, "state/narrative_plan.json")
        write_json(path, plan)
        store.record_artifact(job, "narrative_plan", "state/narrative_plan.json")
        return {
            "job": _get_job_or_404(job_id),
            "narrative_plan": plan,
            "narrative_structure": plan["narrative_structure"],
            "issues": narrative_structure_issues(plan),
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
    asset_path = job_dir / "public" / "game" / asset_relative
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
        avatar_path = job_dir / "public" / "game" / avatar_relative
        avatar_exists = avatar_path.exists()
        avatar_url = f"/play/{job_id}/game/{avatar_relative}"
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
        "url": f"/play/{job_id}/game/{asset_relative}",
        "avatar_exists": avatar_exists,
        "avatar_url": avatar_url,
    }


@app.get("/jobs/{job_id}/assets/review")
def get_asset_review(job_id: str) -> dict[str, Any]:
    job = _get_job_or_404(job_id)
    job_dir = _job_dir_or_404(job_id)
    manifest_path = job_dir / "assets_manifest.json"
    if not manifest_path.exists():
        return {"job": job, "assets": [], "image_enabled": bool(job.get("options", {}).get("generate_assets", False))}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"invalid assets_manifest.json: {exc}") from exc
    images = manifest.get("images", [])
    if not isinstance(images, list):
        raise HTTPException(status_code=422, detail="assets_manifest.json images must be an array")
    character_labels, scene_labels = _asset_review_label_maps(job_dir)
    return {
        "job": job,
        "assets": [_asset_review_item(job_id, job_dir, image, character_labels, scene_labels) for image in images if isinstance(image, dict)],
        "image_enabled": bool(job.get("options", {}).get("generate_assets", False)),
    }


@app.post("/jobs/{job_id}/assets/regenerate")
def regenerate_asset(job_id: str, request: AssetRegenerateRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    filename = request.filename.replace("\\", "/").split("/")[-1].removesuffix(".webp")
    if not filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="invalid asset filename")
    if request.background:
        job = _get_job_or_404(job_id)
        background_tasks.add_task(run_asset_regeneration_background, job_id, filename, request.prompt)
        job["status"] = "QUEUED"
        job["phase"] = "ASSET_GENERATION"
        store.save(job)
        return {"job": job, "queued": True, "filename": filename}
    try:
        job = _get_job_or_404(job_id)
        image = pipeline.regenerate_asset_image(job, filename, request.prompt)
        return {"job": _get_job_or_404(job_id), "queued": False, "asset": image}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PipelineError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/jobs/{job_id}/run")
def run_job(job_id: str, request: RunJobRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    if request.background:
        job = _get_job_or_404(job_id)
        background_tasks.add_task(run_pipeline_background, job_id)
        job["status"] = "QUEUED"
        store.save(job)
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
    request: RunJobRequest = RunJobRequest(),
) -> dict[str, Any]:
    if phase not in pipeline.phase_names():
        raise HTTPException(status_code=422, detail=f"unknown phase: {phase}")
    if request.background:
        job = _get_job_or_404(job_id)
        background_tasks.add_task(run_phase_background, job_id, phase)
        job["status"] = "QUEUED"
        job["phase"] = phase.upper()
        store.save(job)
        return job
    try:
        return pipeline.run_phase(job_id, phase)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PipelineError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/jobs/{job_id}/artifacts")
def list_artifacts(job_id: str) -> dict[str, Any]:
    try:
        return {"job_id": job_id, "artifacts": store.list_artifacts(job_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/jobs/{job_id}/artifacts/{artifact_path:path}")
def get_artifact(job_id: str, artifact_path: str) -> FileResponse:
    if contains_hidden_path(artifact_path):
        raise HTTPException(status_code=404, detail="artifact not found")
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
    return _file_response_under_root(
        root=job_dir / "public" / "game",
        file_path=file_path,
        missing_detail=f"game asset not found: {file_path}",
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
        pipeline.run_phase(job_id, phase)
    except Exception:
        logging.getLogger("uvicorn.error").exception("Forge pipeline phase failed for job_id=%s phase=%s", job_id, phase)


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
