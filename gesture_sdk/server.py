"""Independent, cookie-free static origin for APPROVED public AR works only.

Deploy on a DIFFERENT HTTPS origin from the main NarrativeOS app, never as a
path on the authenticated site. The shared jobs volume is mounted read-only.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response

from gesture_sdk.review import reviewed_ar_html

ID = re.compile(r"^[0-9a-f]{32}$")
ASSET = re.compile(
    r"^(?:hand-gesture-kit\.esm\.js|nar-controls\.esm\.js|"
    r"models/hand_landmarker\.task|wasm/[a-zA-Z0-9_.-]+\.(?:js|wasm|data))$"
)
SCRIPT = re.compile(r"<script>(.*?)</script>", re.DOTALL)
FRAME_ANCESTORS = "https://www.narrativeos.cn https://narrativeos.cn http://localhost:3001 http://127.0.0.1:3001"


def create_app(works_root: Path | None = None, assets_root: Path | None = None) -> FastAPI:
    root = (works_root or Path("/data/jobs/.nar-works")).resolve()
    assets = (assets_root or (Path(__file__).parent / "dist/gesture-sdk/v1")).resolve()
    app = FastAPI(title="NarrativeOS Isolated AR Player", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    def health():
        return {"ready": root.is_dir() and assets.is_dir()}

    @app.get("/gesture-sdk/v1/{name:path}")
    def sdk_asset(name: str):
        if not ASSET.fullmatch(name):
            raise HTTPException(404)
        target = (assets / name).resolve()
        if not target.is_relative_to(assets) or not target.is_file():
            raise HTTPException(404)
        media = ("application/wasm" if name.endswith(".wasm") else
                 "application/octet-stream" if name.endswith((".task", ".data")) else
                 "text/javascript")
        return FileResponse(target, media_type=media, headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
            "Cross-Origin-Resource-Policy": "same-origin",
        })

    @app.get("/works/{work_id}/index.html")
    def public_work(work_id: str):
        if not ID.fullmatch(work_id):
            raise HTTPException(404)
        work_dir = (root / work_id).resolve()
        if not work_dir.is_relative_to(root):
            raise HTTPException(404)
        try:
            work = json.loads((work_dir / "work.json").read_text("utf-8"))
            version = work["published_version_id"]
            if (work["id"] != work_id or work["kind"] != "html" or
                work["publication_status"] not in ("published", "publishing") or
                not ID.fullmatch(version) or
                not any(item.get("id") == version for item in work["versions"])):
                raise ValueError("not a published work")
            target = (work_dir / "versions" / version / "index.html").resolve()
            if not target.is_relative_to(work_dir):
                raise ValueError("untrusted artifact path")
            content = target.read_bytes()
        except (OSError, KeyError, ValueError, TypeError, AttributeError):
            raise HTTPException(404, "AR work not published") from None
        if not reviewed_ar_html(content):
            raise HTTPException(404, "AR template not approved")
        scripts = SCRIPT.findall(content.decode("utf-8"))
        if len(scripts) != 1:
            raise HTTPException(404, "invalid reviewed template")
        digest = base64.b64encode(hashlib.sha256(scripts[0].encode("utf-8")).digest()).decode("ascii")
        csp = (
            "default-src 'none'; "
            f"script-src 'self' 'sha256-{digest}' 'wasm-unsafe-eval'; "
            "style-src 'unsafe-inline'; img-src data: blob:; media-src blob:; "
            "connect-src 'self'; worker-src 'self' blob:; "
            "base-uri 'none'; form-action 'none'; object-src 'none'; "
            f"frame-ancestors {FRAME_ANCESTORS}"
        )
        return Response(content, media_type="text/html; charset=utf-8", headers={
            "Content-Security-Policy": csp,
            "Permissions-Policy": "camera=(self), microphone=(), geolocation=()",
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "Cross-Origin-Resource-Policy": "same-origin",
        })

    return app


app = create_app()
