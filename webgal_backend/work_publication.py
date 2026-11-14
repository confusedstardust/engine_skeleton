"""Teacher-ecosystem publication bridge for verified saved HTML works.

The existing TeacherEcosystem client owns the service contract and authentication.
Only a successfully confirmed publication becomes publicly readable. Unpublish
revokes public content first, so a remote service outage cannot leak a draft.
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .teacher_ecosystem import TeacherEcosystemError, publish_work, unpublish_work
from .work_store import WorkConflictError, WorkStore


class PublicationInput(BaseModel):
    model_config = {"extra": "forbid"}
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(default="", max_length=2000)
    subject: str | None = Field(default=None, max_length=80)
    grade: str | None = Field(default=None, max_length=80)
    tags: list[str] = Field(default_factory=list, max_length=8)


def create_router(*, user_for_request, store: WorkStore | None = None,
                  publisher=None, unpublisher=None, frontend_url: str | None = None):
    router = APIRouter(prefix="/works", tags=["Work publication"])
    works = store or WorkStore()
    publisher = publisher or publish_work
    unpublisher = unpublisher or unpublish_work
    root = (frontend_url or os.getenv("WEBGAL_FRONTEND_URL") or "http://127.0.0.1:3001").rstrip("/")

    async def identity(request: Request) -> dict[str, Any]:
        user = await run_in_threadpool(user_for_request, request)
        if user.get("auth_type") != "sso" or not user.get("id"):
            raise HTTPException(401, "请先登录 NarrativeOS")
        return user

    def mutation(request: Request):
        if request.headers.get("x-naragent-action") != "chat":
            raise HTTPException(403, "缺少作品操作请求校验标识")

    @router.get("/{work_id}/publication")
    async def status(work_id: str, request: Request):
        user = await identity(request)
        try:
            work = await run_in_threadpool(works.get, str(user["id"]), work_id)
        except FileNotFoundError:
            raise HTTPException(404, "作品不存在") from None
        return {
            "published": work.get("publication_status") == "published",
            "status": work.get("publication_status", "draft"),
            "public_url": work.get("public_url") if work.get("publication_status") == "published" else None,
            "published_version_id": work.get("published_version_id"),
        }

    @router.post("/{work_id}/publication")
    async def publish(work_id: str, payload: PublicationInput, request: Request):
        mutation(request)
        user = await identity(request)
        owner = str(user["id"])
        try:
            work = await run_in_threadpool(works.get, owner, work_id)
        except FileNotFoundError:
            raise HTTPException(404, "作品不存在") from None
        snapshot = {
            "title": payload.title.strip(), "summary": payload.summary.strip(),
            "subject": payload.subject.strip() if payload.subject else None,
            "grade": payload.grade.strip() if payload.grade else None,
            "tags": [tag.strip()[:40] for tag in payload.tags if tag.strip()],
        }
        if (work.get("publication_status") == "published" and
                work.get("published_version_id") == work["current_version_id"] and
                work.get("published_metadata") == snapshot):
            return {"published": True, "status": "published", "public_url": work["public_url"]}
        play_url = f"{root}/practice/works/{work_id}"
        cover_url = f"{root}/api/forge/public/works/{work_id}/cover.png"
        try:
            pending = await run_in_threadpool(works.start_publication, owner, work_id)
        except WorkConflictError:
            raise HTTPException(409, "作品尚不能发布或已有发布任务正在进行") from None
        version_id = pending["pending_version_id"]
        body = {
            "ownerUserId": owner, "authorName": user.get("nickname") or (user.get("email") or "").split("@")[0] or "NarrativeOS 教师",
            "jobId": work_id, "resourceType": "INTERACTIVE_HTML",
            "title": snapshot["title"], "summary": snapshot["summary"],
            "subject": snapshot["subject"], "grade": snapshot["grade"], "tags": snapshot["tags"],
            "coverUrl": cover_url, "playUrl": play_url, "quizUrl": None,
        }
        try:
            remote = await run_in_threadpool(publisher, body)
            if remote.get("published") is not True:
                raise TeacherEcosystemError("Teacher ecosystem did not confirm publication")
            await run_in_threadpool(works.finish_publication, owner, work_id, version_id, play_url, snapshot)
        except (TeacherEcosystemError, WorkConflictError, OSError, ValueError, AttributeError):
            await run_in_threadpool(works.rollback_publication, owner, work_id)
            raise HTTPException(503, "教师资源广场暂时无法完成发布，私有作品已保留，请稍后重试") from None
        return {"published": True, "status": "published", "public_url": play_url,
                "published_version_id": version_id}

    @router.delete("/{work_id}/publication")
    async def unpublish(work_id: str, request: Request):
        mutation(request)
        user = await identity(request)
        owner = str(user["id"])
        try:
            await run_in_threadpool(works.start_unpublish, owner, work_id)
        except FileNotFoundError:
            raise HTTPException(404, "作品不存在") from None
        except WorkConflictError:
            raise HTTPException(409, "作品尚未发布") from None
        try:
            await run_in_threadpool(unpublisher, owner, work_id)
            await run_in_threadpool(works.finish_unpublish, owner, work_id)
        except (TeacherEcosystemError, OSError, ValueError):
            # Public access stays revoked even if ecosystem de-indexing must be retried.
            raise HTTPException(503, "公开访问已关闭；教师广场撤回暂未完成，请重试") from None
        return {"published": False, "status": "unpublished", "public_url": None}

    return router


def create_public_router(*, store: WorkStore | None = None):
    router = APIRouter(prefix="/public/works", tags=["Public interactive works"])
    works = store or WorkStore()

    @router.get("/{work_id}")
    async def published_metadata(work_id: str):
        try:
            return await run_in_threadpool(works.public, work_id)
        except FileNotFoundError:
            raise HTTPException(404, "公开作品不存在或已撤回") from None

    @router.get("/{work_id}/index.html")
    async def published_html(work_id: str):
        try:
            content = await run_in_threadpool(works.public_asset, work_id, "index.html")
        except (FileNotFoundError, OSError):
            raise HTTPException(404, "公开作品不存在或已撤回") from None
        return Response(content, media_type="text/html", headers={
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'",
        })

    @router.get("/{work_id}/cover.png")
    async def published_cover(work_id: str):
        try:
            content = await run_in_threadpool(works.public_cover, work_id)
        except (FileNotFoundError, OSError):
            raise HTTPException(404, "公开作品不存在或已撤回") from None
        return Response(content, media_type="image/png", headers={
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        })

    return router
