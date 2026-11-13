"""Share metadata and QR are available only for confirmed public works.

Creator ownership is checked for both endpoints. Never generate public links
for private, failed, pending or withdrawn works.
"""
from __future__ import annotations

import io
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from .work_store import WorkStore


def create_router(*, user_for_request, store: WorkStore | None = None,
                  frontend_url: str | None = None):
    router = APIRouter(prefix="/works", tags=["Published work sharing"])
    works = store or WorkStore()
    root = (frontend_url or os.getenv("WEBGAL_FRONTEND_URL") or "http://127.0.0.1:3001").rstrip("/")

    async def shared(owner_request: Request, work_id: str) -> dict:
        user = await run_in_threadpool(user_for_request, owner_request)
        if user.get("auth_type") != "sso" or not user.get("id"):
            raise HTTPException(401, "请先登录 NarrativeOS")
        try:
            saved = await run_in_threadpool(works.get, str(user["id"]), work_id)
        except FileNotFoundError:
            raise HTTPException(404, "作品不存在") from None
        if saved.get("publication_status") != "published" or not saved.get("public_url"):
            raise HTTPException(409, "只有成功发布到教师资源广场的作品才允许分享")
        # Source only from trusted service-side publication metadata.
        public = await run_in_threadpool(works.public, work_id)
        return {
            "work_id": work_id,
            "title": public["title"],
            "summary": public.get("summary", ""),
            "public_url": saved["public_url"],
            "cover_url": f"{root}/api/forge/public/works/{work_id}/cover.png",
        }

    @router.get("/{work_id}/share")
    async def share(work_id: str, request: Request):
        return await shared(request, work_id)

    @router.get("/{work_id}/share/qr.png")
    async def share_qr(work_id: str, request: Request):
        payload = await shared(request, work_id)
        import qrcode  # Backend requirements already include qrcode>=8.
        from qrcode.constants import ERROR_CORRECT_M
        qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=8, border=3)
        qr.add_data(payload["public_url"])
        qr.make(fit=True)
        image = qr.make_image(fill_color="#25382a", back_color="white")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return Response(buffer.getvalue(), media_type="image/png", headers={
            "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        })

    return router
