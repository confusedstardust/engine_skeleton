from __future__ import annotations

import json
import logging
import hashlib
import mimetypes
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import artifacts, game_design
from .artifacts import contains_hidden_path
from .config import settings
from .game_project import GameProjectError, completed_from_game_project, game_project_from_completed
from .job_options import GenerationOptions, normalize_generation_options
from .narrative_nodes import NarrativeNodeError, NarrativeNodeKind, generate_narrative_node as generate_narrative_node_payload
from .narrative_structure import build_synced_narrative_structure, narrative_structure_issues
from .pipeline import PipelineError, WebGALPipeline
from .publisher import (
    PublishError,
    activate_game_revision,
    current_publication,
    list_game_revisions,
    published_game_root,
    revision_game_root,
)
from .scene_plan import build_scene_plan
from .storage import (
    ConcurrentJobUpdateError,
    JobBusyError,
    JobStore,
    read_json,
    utc_now,
    write_json,
    write_text_atomic,
)
from .task_queue import DurableTaskQueue, DurableTaskWorker, QueueBusyError, QueuedTask


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logging.getLogger("uvicorn.error").info(
        "WebGAL paths: contracts_dir=%s asset_scripts_dir=%s",
        settings.contracts_dir,
        settings.asset_scripts_dir,
    )
    queue_recovery = task_queue.recover_expired()
    for job_id in [*queue_recovery["failed_job_ids"], *queue_recovery["abandoned_preparing_job_ids"]]:
        _mark_queue_recovery_failed(job_id)
    cleared_reservations = store.clear_inactive_run_reservations(task_queue.active_run_ids())
    if cleared_reservations:
        logging.getLogger("uvicorn.error").warning(
            "Cleared %s stale task reservations from WebGAL jobs", cleared_reservations
        )
    recovered = store.recover_stale_running_jobs(protected_job_ids=task_queue.active_job_ids())
    if recovered:
        logging.getLogger("uvicorn.error").warning("Recovered %s interrupted WebGAL jobs", recovered)
    task_worker.start()
    task_worker.notify()
    try:
        yield
    finally:
        task_worker.stop()


app = FastAPI(title="WebGAL Forge", version="1.0.0", redirect_slashes=False, lifespan=lifespan)


@app.exception_handler(ConcurrentJobUpdateError)
async def concurrent_job_update_handler(_request: Request, exc: ConcurrentJobUpdateError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc), "code": "concurrent_job_update"})


store = JobStore()
pipeline = WebGALPipeline(store)
task_queue = DurableTaskQueue(settings.jobs_dir / "task_runs.sqlite3")
frontend_dir = settings.workspace_root / "forge_frontend"
engine_dist_dir = settings.workspace_root / "dist"
frontend_url = os.getenv("WEBGAL_FRONTEND_URL", "http://127.0.0.1:3001")
INVITE_HEADER_NAME = "X-WebGAL-Invite-Code"
INVITE_CODES_ENV = "WEBGAL_INVITE_CODES"
INVITE_CODES_FILE_ENV = "WEBGAL_INVITE_CODES_FILE"


def _execute_queued_task(task: QueuedTask) -> None:
    try:
        reserved_job = store.get(task.job_id)
        if reserved_job.get("active_run_id") != task.id:
            raise PipelineError(
                f"queued task does not match the job reservation: run_id={task.id} "
                f"active_run_id={reserved_job.get('active_run_id')}"
            )
        if task.task_type == "pipeline":
            pipeline.run_all(task.job_id)
        elif task.task_type == "phase" and task.phase:
            pipeline.run_phase(task.job_id, task.phase)
        elif task.task_type == "asset_regeneration":
            with store.execution(task.job_id):
                job = store.get(task.job_id)
                pipeline.regenerate_asset_image(
                    job,
                    str(task.payload.get("filename") or ""),
                    task.payload.get("prompt"),
                )
        else:
            raise PipelineError(f"unsupported queued task type: {task.task_type}")
    except Exception as exc:
        if task.task_type == "asset_regeneration":
            try:
                store.set_error(store.get(task.job_id), str(exc))
            except FileNotFoundError:
                pass
        logging.getLogger("uvicorn.error").exception(
            "Durable WebGAL task failed: run_id=%s job_id=%s type=%s phase=%s",
            task.id,
            task.job_id,
            task.task_type,
            task.phase,
        )
        raise


def _finalize_queued_task(task: QueuedTask, status: str, error: str | None) -> None:
    try:
        job = store.get(task.job_id)
    except FileNotFoundError:
        return
    if job.get("active_run_id") != task.id:
        return
    if status == "FAILED" and job.get("status") != "FAILED":
        store.set_error(job, error or "background task failed")
    job["active_run_id"] = None
    store.save(job)


def _mark_queue_recovery_failed(job_id: str) -> None:
    try:
        job = store.get(job_id)
        store.set_error(job, "background task could not be recovered; rerun the interrupted phase")
        job["active_run_id"] = None
        store.save(job)
    except FileNotFoundError:
        pass


task_worker = DurableTaskWorker(
    task_queue,
    _execute_queued_task,
    recovery_failure_handler=_mark_queue_recovery_failed,
    terminal_handler=_finalize_queued_task,
)


def _job_has_active_task(job_id: str) -> bool:
    return task_queue.has_active(job_id) or store.is_execution_active(job_id)


def _enqueue_job_task(
    job: dict[str, Any],
    task_type: str,
    *,
    phase: str | None = None,
    payload: dict[str, Any] | None = None,
) -> str:
    try:
        run_id = task_queue.prepare(job["id"], task_type, phase=phase, payload=payload)
    except QueueBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        store.transition(job, "QUEUED", phase.upper() if phase else task_type.upper())
        job["active_run_id"] = run_id
        store.save(job)
        task_queue.activate(run_id)
    except Exception as exc:
        task_queue.cancel_prepared(run_id, f"job state update failed: {exc}")
        try:
            failed_job = store.get(job["id"])
            store.set_error(failed_job, "task could not be queued consistently; please retry")
            failed_job["active_run_id"] = None
            store.save(failed_job)
        except Exception:
            logging.getLogger("uvicorn.error").exception(
                "Failed to compensate job state after queue preparation failure: job_id=%s run_id=%s",
                job["id"],
                run_id,
            )
        raise HTTPException(status_code=503, detail="task could not be queued consistently; please retry") from exc
    task_worker.notify()
    return run_id


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
def create_job(request: CreateJobRequest, http_request: Request) -> dict[str, Any]:
    identity = _identity_from_request(http_request)
    return store.create(request.source_material, normalize_generation_options(request.options), identity=identity)


@app.get("/jobs")
def list_jobs(request: Request) -> dict[str, Any]:
    identity = _identity_from_request(request)
    jobs = [job for job in store.list_all() if _job_belongs_to_identity(job, identity)]
    return {"jobs": jobs}


@app.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request) -> dict[str, Any]:
    return _get_owned_job_or_404(job_id, request)


@app.get("/jobs/{job_id}/runs")
def get_job_runs(job_id: str, request: Request) -> dict[str, Any]:
    _get_owned_job_or_404(job_id, request)
    return {"job_id": job_id, "runs": task_queue.list_for_job(job_id)}


@app.get("/jobs/{job_id}/publication")
def get_job_publication(job_id: str, request: Request) -> dict[str, Any]:
    _get_owned_job_or_404(job_id, request)
    job_dir = store.job_dir(job_id)
    return {
        "job_id": job_id,
        "publication": current_publication(job_dir),
        "revisions": list_game_revisions(job_dir),
    }


@app.post("/jobs/{job_id}/publication/{revision_id}/activate")
def activate_job_publication(job_id: str, revision_id: str, request: Request) -> dict[str, Any]:
    job = _get_owned_job_or_404(job_id, request)
    if _job_has_active_task(job_id):
        raise HTTPException(status_code=409, detail="job is running; wait before changing the published revision")
    try:
        publication = activate_game_revision(store.job_dir(job_id), revision_id)
    except PublishError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    store.record_artifact(job, "published_revision", "state/published_revision.json")
    job["published_revision"] = publication["revision_id"]
    job["published_root_hash"] = publication["root_hash"]
    job.setdefault("history", []).append(
        {
            "at": utc_now(),
            "status": job.get("status"),
            "event": "PUBLICATION_ACTIVATED",
            "revision_id": publication["revision_id"],
        }
    )
    store.save(job)
    return {
        "job_id": job_id,
        "job": job,
        "publication": publication,
        "revisions": list_game_revisions(store.job_dir(job_id)),
    }


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
        if _job_has_active_task(job_id):
            raise HTTPException(status_code=409, detail="job is running; wait for the current phase before editing artifacts")
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
            parsed_content = json.loads(request.content)
            if relative == "state/game_design_completed.json":
                if not isinstance(parsed_content, dict):
                    raise HTTPException(status_code=422, detail="game_design_completed.json must be a JSON object")
                topology_errors = game_design.completed_topology_errors(parsed_content)
                if topology_errors:
                    raise HTTPException(
                        status_code=422,
                        detail={"code": "invalid_scene_topology", "errors": topology_errors},
                    )
                project_path = store.artifact_path(job_id, "state/game_project.json")
                previous_project = read_json(project_path) if project_path.exists() else None
                try:
                    project = game_project_from_completed(parsed_content, previous=previous_project)
                except GameProjectError as exc:
                    raise HTTPException(status_code=422, detail={"code": "invalid_game_project", "message": str(exc)}) from exc
                write_json(project_path, project.model_dump(mode="json"))
                store.record_artifact(job, "game_project", "state/game_project.json")
                parsed_content = completed_from_game_project(project)
            write_json(path, parsed_content)
        else:
            write_text_atomic(path, request.content.rstrip() + "\n")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"invalid JSON: {exc}") from exc

    store.record_artifact(job, artifacts.artifact_key_for_path(relative), relative)
    if relative.startswith("public/game/scene/"):
        store.mark_artifacts_stale(job, {"validation_report"}, because=relative)
    return {"job": _get_owned_job_or_404(job_id, http_request), "path": relative, "saved": True}


@app.post("/jobs/{job_id}/narrative-node")
def generate_narrative_node(job_id: str, request: GenerateNarrativeNodeRequest, http_request: Request) -> dict[str, Any]:
    try:
        _get_owned_job_or_404(job_id, http_request)
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
def sync_narrative_structure(job_id: str, request: SyncNarrativeStructureRequest, http_request: Request) -> dict[str, Any]:
    try:
        job = _get_owned_job_or_404(job_id, http_request)
        if _job_has_active_task(job_id):
            raise HTTPException(status_code=409, detail="job is running; wait for the current phase before syncing structure")
        plan = dict(request.narrative_plan)
        plan["narrative_structure"] = build_synced_narrative_structure(plan)
        path = store.artifact_path(job_id, "state/narrative_plan.json")
        write_json(path, plan)
        store.record_artifact(job, "narrative_plan", "state/narrative_plan.json")
        return {
            "job": _get_owned_job_or_404(job_id, http_request),
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
        avatar_url = _public_app_path(f"/preview/{job_id}/game/{avatar_relative}")
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
        "url": _public_app_path(f"/preview/{job_id}/game/{asset_relative}"),
        "avatar_exists": avatar_exists,
        "avatar_url": avatar_url,
    }


@app.get("/jobs/{job_id}/assets/review")
def get_asset_review(job_id: str, request: Request) -> dict[str, Any]:
    job = _get_owned_job_or_404(job_id, request)
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
def regenerate_asset(
    job_id: str,
    request: AssetRegenerateRequest,
    http_request: Request,
) -> dict[str, Any]:
    filename = request.filename.replace("\\", "/").split("/")[-1].removesuffix(".webp")
    if not filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="invalid asset filename")
    if request.background:
        job = _get_owned_job_or_404(job_id, http_request)
        run_id = _enqueue_job_task(
            job,
            "asset_regeneration",
            phase="asset_generation",
            payload={"filename": filename, "prompt": request.prompt},
        )
        return {"job": job, "queued": True, "filename": filename, "run_id": run_id}
    try:
        job = _get_owned_job_or_404(job_id, http_request)
        if _job_has_active_task(job_id):
            raise HTTPException(status_code=409, detail=f"job already has a queued or running task: {job_id}")
        with store.execution(job_id):
            image = pipeline.regenerate_asset_image(job, filename, request.prompt)
        return {"job": _get_owned_job_or_404(job_id, http_request), "queued": False, "asset": image}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PipelineError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/jobs/{job_id}/run")
def run_job(job_id: str, request: RunJobRequest, http_request: Request) -> dict[str, Any]:
    _get_owned_job_or_404(job_id, http_request)
    if request.background:
        job = _get_owned_job_or_404(job_id, http_request)
        _enqueue_job_task(job, "pipeline")
        return job
    try:
        if _job_has_active_task(job_id):
            raise HTTPException(status_code=409, detail=f"job already has a queued or running task: {job_id}")
        return pipeline.run_all(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PipelineError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except JobBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/jobs/{job_id}/phases/{phase}")
def run_phase(
    job_id: str,
    phase: str,
    http_request: Request,
    request: RunJobRequest = RunJobRequest(),
) -> dict[str, Any]:
    if phase not in pipeline.phase_names():
        raise HTTPException(status_code=422, detail=f"unknown phase: {phase}")
    _get_owned_job_or_404(job_id, http_request)
    if request.background:
        job = _get_owned_job_or_404(job_id, http_request)
        _enqueue_job_task(job, "phase", phase=phase)
        return job
    try:
        if _job_has_active_task(job_id):
            raise HTTPException(status_code=409, detail=f"job already has a queued or running task: {job_id}")
        return pipeline.run_phase(job_id, phase)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PipelineError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except JobBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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
    job = _get_job_or_404(job_id)
    job_dir = store.job_dir(job_id)
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    game_root = published_game_root(job_dir, fallback_to_working=not bool(job.get("publication_required", False)))
    if game_root is None:
        raise HTTPException(status_code=409, detail="game has not been published yet")
    return _file_response_under_root(
        root=game_root,
        file_path=file_path,
        missing_detail=f"game asset not found: {file_path}",
    )


@app.get("/preview/{job_id}/game/{file_path:path}")
def preview_game_asset(job_id: str, file_path: str) -> FileResponse:
    if contains_hidden_path(file_path):
        raise HTTPException(status_code=404, detail=f"preview asset not found: {file_path}")
    job_dir = _job_dir_or_404(job_id)
    return _file_response_under_root(
        root=job_dir / "public" / "game",
        file_path=file_path,
        missing_detail=f"preview asset not found: {file_path}",
    )


@app.get("/play/game/{file_path:path}")
def play_game_asset_from_referer(file_path: str, request: Request) -> FileResponse:
    referer = request.headers.get("referer", "")
    match = re.search(r"/play/([A-Za-z0-9_-]+)(?:/|$)", referer)
    if not match:
        raise HTTPException(status_code=404, detail=f"game asset not found: {file_path}")
    return play_game_asset(match.group(1), file_path)


@app.get("/play/{job_id}/revisions/{revision_id}/game/{file_path:path}")
def play_revision_game_asset(job_id: str, revision_id: str, file_path: str) -> FileResponse:
    if contains_hidden_path(file_path):
        raise HTTPException(status_code=404, detail=f"game asset not found: {file_path}")
    job_dir = _job_dir_or_404(job_id)
    game_root = revision_game_root(job_dir, revision_id)
    if game_root is None:
        raise HTTPException(status_code=404, detail=f"published revision not found: {revision_id}")
    return _file_response_under_root(
        root=game_root,
        file_path=file_path,
        missing_detail=f"game asset not found: {file_path}",
    )


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
    job = _get_job_or_404(job_id)
    job_dir = store.job_dir(job_id)
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    if not engine_dist_dir.exists():
        raise HTTPException(status_code=404, detail="engine not built; run npm run build first")

    index_path = engine_dist_dir / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="engine index.html not found")
    publication = current_publication(job_dir)
    if published_game_root(job_dir, fallback_to_working=not bool(job.get("publication_required", False))) is None:
        raise HTTPException(status_code=409, detail="game has not been published yet")

    play_root = _public_app_path(f"/play/{job_id}/")
    asset_root = _public_app_path(f"/play/{job_id}/assets/")
    game_root = (
        _public_app_path(f"/play/{job_id}/revisions/{publication['revision_id']}/game/")
        if publication
        else _public_app_path(f"/play/{job_id}/game/")
    )
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


def _read_narrative_plan(job_id: str) -> dict[str, Any]:
    path = store.artifact_path(job_id, "state/narrative_plan.json")
    if not path.exists():
        raise FileNotFoundError(f"narrative plan not found for job_id={job_id}")
    return json.loads(path.read_text(encoding="utf-8"))
