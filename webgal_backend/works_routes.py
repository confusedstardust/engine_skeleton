"""SSO-only NarrativeOS Works API, reusing the existing Forge jobs volume.

Private NarAgent artifacts are imported using service-to-service authentication.
No user-provided URL, object key, HTML bytes or owner ID is trusted.
"""
from __future__ import annotations

import os
import re
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .work_store import ASSET_LIMITS, WorkConflictError, WorkStore

ID_PATTERN = r"^[0-9a-f]{32}$"


class SaveWorkInput(BaseModel):
    model_config = {"extra": "forbid"}
    artifact_id: str = Field(pattern=ID_PATTERN)
    kind: Literal["html", "animation"]
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(default="", max_length=2000)


class UpdateWorkInput(BaseModel):
    model_config = {"extra": "forbid"}
    title: str | None = Field(default=None, min_length=1, max_length=160)
    summary: str | None = Field(default=None, max_length=2000)
    subject: str | None = Field(default=None, max_length=80)
    grade: str | None = Field(default=None, max_length=80)
    tags: list[str] | None = Field(default=None, max_length=8)


class AddVersionInput(BaseModel):
    model_config = {"extra": "forbid"}
    artifact_id: str = Field(pattern=ID_PATTERN)
    expected_parent_artifact_id: str = Field(pattern=ID_PATTERN)


def create_router(*, user_for_request, store: WorkStore | None = None, transport=None):
    router = APIRouter(prefix="/works", tags=["NarAgent works"])
    works = store or WorkStore()

    async def owner_from(request: Request) -> str:
        user = await run_in_threadpool(user_for_request, request)
        if user.get("auth_type") != "sso" or not user.get("id"):
            raise HTTPException(401, "请先登录 NarrativeOS")
        return str(user["id"])

    def require_mutation(request: Request):
        if request.headers.get("x-naragent-action") != "chat":
            raise HTTPException(403, "缺少作品操作请求校验标识")

    async def source_artifact(owner: str, identifier: str, kind: str,
                              parent_artifact_id: str | None = None) -> dict[str, bytes]:
        token = os.getenv("NAR_AGENT_SERVICE_TOKEN", "")
        if len(token) < 32:
            raise HTTPException(503, "NarAgent 服务未配置")
        base = os.getenv("NAR_AGENT_URL", "http://127.0.0.1:8020").rstrip("/")
        headers = {"Authorization": "Bearer " + token, "X-User-ID": owner}
        try:
            async with httpx.AsyncClient(timeout=25, transport=transport, follow_redirects=False, trust_env=False) as client:
                response = await client.get(f"{base}/v1/artifacts/{identifier}/metadata", headers=headers)
                if response.status_code == 404:
                    raise HTTPException(404, "产物不存在或无权访问")
                response.raise_for_status()
                metadata = response.json()
                if metadata.get("kind") != kind or not metadata.get("passed"):
                    raise HTTPException(422, "产物类型或生成检查结果无效")
                if parent_artifact_id is not None and metadata.get("parent_artifact_id") != parent_artifact_id:
                    raise HTTPException(409, "新版本并非基于当前作品生成")
                content = {}
                for filename, limit in ASSET_LIMITS.items():
                    resp = await client.get(f"{base}/v1/artifacts/{identifier}/{filename}", headers=headers)
                    if resp.status_code == 404:
                        raise HTTPException(404, "产物文件不存在或无权访问")
                    resp.raise_for_status()
                    if len(resp.content) > limit or not resp.content:
                        raise HTTPException(422, "作品文件过大或为空")
                    content[filename] = resp.content
                return content
        except httpx.HTTPError:
            raise HTTPException(503, "暂时无法连接作品生成服务，请稍后重试") from None
        except (ValueError, KeyError):
            raise HTTPException(503, "作品生成服务响应无效") from None

    @router.post("", status_code=201)
    async def save_work(payload: SaveWorkInput, request: Request):
        require_mutation(request)
        owner = await owner_from(request)
        existing = await run_in_threadpool(works.find_by_artifact, owner, payload.artifact_id)
        if existing is not None:
            return {"work": existing}
        assets = await source_artifact(owner, payload.artifact_id, payload.kind)
        work = await run_in_threadpool(works.create, owner, payload.artifact_id,
                                       payload.kind, payload.title, payload.summary, assets)
        return {"work": work}

    @router.get("")
    async def list_works(request: Request):
        owner = await owner_from(request)
        return {"works": await run_in_threadpool(works.list_for, owner)}

    @router.get("/{work_id}")
    async def get_work(work_id: str, request: Request):
        owner = await owner_from(request)
        try:
            return {"work": await run_in_threadpool(works.get, owner, work_id)}
        except FileNotFoundError:
            raise HTTPException(404, "作品不存在") from None

    @router.patch("/{work_id}")
    async def update_work(work_id: str, payload: UpdateWorkInput, request: Request):
        require_mutation(request)
        owner = await owner_from(request)
        fields = payload.model_dump(exclude_unset=True)
        if "tags" in fields and fields["tags"] is not None:
            fields["tags"] = [tag.strip()[:40] for tag in fields["tags"] if tag.strip()]
        try:
            work = await run_in_threadpool(works.update, owner, work_id, **fields)
            return {"work": work}
        except FileNotFoundError:
            raise HTTPException(404, "作品不存在") from None

    @router.post("/{work_id}/versions")
    async def add_version(work_id: str, payload: AddVersionInput, request: Request):
        require_mutation(request)
        owner = await owner_from(request)
        try:
            current = await run_in_threadpool(works.get, owner, work_id)
            files = await source_artifact(owner, payload.artifact_id, current["kind"],
                                          payload.expected_parent_artifact_id)
            work = await run_in_threadpool(works.add_version, owner, work_id,
                                           payload.artifact_id, files, payload.expected_parent_artifact_id)
            return {"work": work}
        except FileNotFoundError:
            raise HTTPException(404, "作品不存在") from None
        except WorkConflictError:
            raise HTTPException(409, "作品当前版本已变化，请刷新后再试") from None

    @router.get("/{work_id}/assets/{version_id}/{filename}")
    async def asset(work_id: str, version_id: str, filename: str, request: Request):
        owner = await owner_from(request)
        try:
            content = await run_in_threadpool(works.asset, owner, work_id, version_id, filename)
        except (FileNotFoundError, ValueError, OSError):
            raise HTTPException(404, "作品文件不存在") from None
        return Response(content, media_type="text/html" if filename == "index.html" else "image/png", headers={
            "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'",
        })

    return router
