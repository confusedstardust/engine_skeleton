from __future__ import annotations

import logging
import mimetypes
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import settings
from .pipeline import PipelineError, WebGALPipeline
from .storage import JobStore


app = FastAPI(title="WebGAL Forge", version="1.0.0")
store = JobStore()
pipeline = WebGALPipeline(store)
frontend_dir = settings.workspace_root / "forge_frontend"
engine_dist_dir = settings.workspace_root / "dist"


if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


@app.on_event("startup")
def log_runtime_paths() -> None:
    logging.getLogger("uvicorn.error").info(
        "WebGAL paths: skill_dir=%s asset_scripts_dir=%s",
        settings.skill_dir,
        settings.asset_scripts_dir,
    )


class CreateJobRequest(BaseModel):
    source_material: str = Field(min_length=1)
    options: dict[str, Any] = Field(default_factory=dict)


class RunJobRequest(BaseModel):
    background: bool = False


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def index() -> FileResponse:
    path = frontend_dir / "index.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="forge_frontend/index.html not found")
    return FileResponse(path)


@app.post("/jobs")
def create_job(request: CreateJobRequest) -> dict[str, Any]:
    return store.create(request.source_material, request.options)


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
    try:
        return store.get(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/jobs/{job_id}/run")
def run_job(job_id: str, request: RunJobRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    if request.background:
        background_tasks.add_task(run_pipeline_background, job_id)
        job = store.get(job_id)
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
def run_phase(job_id: str, phase: str) -> dict[str, Any]:
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
    try:
        path = store.artifact_path(job_id, artifact_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"artifact not found: {artifact_path}")
    return FileResponse(path)


# ──────────────────────────────────────────────────────────────────────────────
# Play routes: serve the built WebGAL engine with game data from a specific job
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/play/{job_id}/game/{file_path:path}")
def play_game_asset(job_id: str, file_path: str) -> FileResponse:
    """Serve game assets from the job's generated output."""
    job_dir = store.job_dir(job_id)
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    asset_path = (job_dir / "public" / "game" / file_path).resolve()
    game_root = (job_dir / "public" / "game").resolve()
    if game_root not in asset_path.parents and game_root != asset_path:
        raise HTTPException(status_code=400, detail="invalid path")
    if not asset_path.exists() or not asset_path.is_file():
        raise HTTPException(status_code=404, detail=f"game asset not found: {file_path}")
    content_type, _ = mimetypes.guess_type(str(asset_path))
    return FileResponse(asset_path, media_type=content_type)


@app.get("/play/{job_id}/assets/{file_path:path}")
def play_engine_asset(job_id: str, file_path: str) -> FileResponse:
    """Serve built engine static assets (JS/CSS/fonts)."""
    if not engine_dist_dir.exists():
        raise HTTPException(status_code=404, detail="engine not built; run npm run build first")
    asset_path = (engine_dist_dir / "assets" / file_path).resolve()
    assets_root = (engine_dist_dir / "assets").resolve()
    if assets_root not in asset_path.parents and assets_root != asset_path:
        raise HTTPException(status_code=400, detail="invalid path")
    if not asset_path.exists() or not asset_path.is_file():
        raise HTTPException(status_code=404, detail=f"engine asset not found: {file_path}")
    content_type, _ = mimetypes.guess_type(str(asset_path))
    return FileResponse(asset_path, media_type=content_type)


@app.get("/play/{job_id}/static-engine/{file_path:path}")
def play_engine_static(job_id: str, file_path: str) -> FileResponse:
    """Serve other engine static files (icons, manifest, etc.)."""
    if not engine_dist_dir.exists():
        raise HTTPException(status_code=404, detail="engine not built")
    asset_path = (engine_dist_dir / file_path).resolve()
    dist_root = engine_dist_dir.resolve()
    if dist_root not in asset_path.parents and dist_root != asset_path:
        raise HTTPException(status_code=400, detail="invalid path")
    if not asset_path.exists() or not asset_path.is_file():
        raise HTTPException(status_code=404, detail=f"not found: {file_path}")
    content_type, _ = mimetypes.guess_type(str(asset_path))
    return FileResponse(asset_path, media_type=content_type)


@app.get("/play/{job_id}/index.html")
@app.get("/play/{job_id}/")
def play_game_with_slash(job_id: str) -> HTMLResponse:
    """Serve the WebGAL engine HTML rewritten to load game data from this job."""
    job_dir = store.job_dir(job_id)
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    if not engine_dist_dir.exists():
        raise HTTPException(status_code=404, detail="engine not built; run npm run build first")

    index_path = engine_dist_dir / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="engine index.html not found")

    html = index_path.read_text(encoding="utf-8")
    html = html.replace('./assets/', f'/play/{job_id}/assets/')
    html = html.replace('./game/', f'/play/{job_id}/game/')
    html = html.replace('./icons/', f'/play/{job_id}/static-engine/icons/')
    html = html.replace('./manifest.json', f'/play/{job_id}/static-engine/manifest.json')
    return HTMLResponse(content=html)


@app.get("/play/{job_id}")
def play_game_redirect(job_id: str, request: Request) -> HTMLResponse:
    """Redirect to trailing-slash version for correct relative path resolution."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"/play/{job_id}/", status_code=301)


def run_pipeline_background(job_id: str) -> None:
    try:
        pipeline.run_all(job_id)
    except Exception:
        return
