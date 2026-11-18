"""No arbitrary generated HTML may be privileged with camera access."""
import json
import re
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gesture_sdk.review import reviewed_ar_html
from gesture_sdk.server import create_app
from nar_agent.app.template_catalog import TemplateCatalog

TEMPLATES = ROOT / "nar_agent" / "templates"
DATA = {"title": "数学探索", "cards": [{"question": "2+3=?", "answer": "5"}]}


def source():
    return TemplateCatalog(TEMPLATES).render("gesture-cards", DATA).encode()


def test_template_is_exact_byte_reviewed():
    good = source()
    assert reviewed_ar_html(good, template_root=TEMPLATES)
    assert not reviewed_ar_html(good + b"<script>console.log('evil')</script>", template_root=TEMPLATES)
    assert not reviewed_ar_html(good.replace(b"gesture-cards", b"unknown-cards", 1), template_root=TEMPLATES)
    assert not reviewed_ar_html(b'<script id="nar-data">{"title":"hi"}</script>', template_root=TEMPLATES)


def test_isolated_origin_publication_gate_and_headers(tmp_path, monkeypatch):
    # Mirror the image layout for a test without importing an authenticated backend.
    from gesture_sdk import review
    monkeypatch.setattr(review, "TEMPLATES", TEMPLATES)
    work_id, version_id = "a" * 32, "b" * 32
    base = tmp_path / ".nar-works" / work_id
    folder = base / "versions" / version_id
    folder.mkdir(parents=True)
    (folder / "index.html").write_bytes(source())
    meta = {"id": work_id, "kind": "html", "publication_status": "draft",
            "published_version_id": version_id, "versions": [{"id": version_id}]}
    (base / "work.json").write_text(json.dumps(meta))
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "nar-controls.esm.js").write_text("export class GestureControls {}")
    app = create_app(tmp_path / ".nar-works", assets)
    client = TestClient(app)
    assert client.get(f"/works/{work_id}/index.html").status_code == 404
    meta["publication_status"] = "published"
    (base / "work.json").write_text(json.dumps(meta))
    # Production template_root is bundled in /app/gesture_sdk/templates.
    # For local tests, temporarily load the same audited template there.
    original = review.reviewed_ar_html
    monkeypatch.setattr("gesture_sdk.server.reviewed_ar_html",
        lambda content: original(content, template_root=TEMPLATES))
    response = client.get(f"/works/{work_id}/index.html")
    assert response.status_code == 200
    assert "sha256-" in response.headers["Content-Security-Policy"]
    assert "frame-ancestors https://www.narrativeos.cn" in response.headers["Content-Security-Policy"]
    assert response.headers["Permissions-Policy"].startswith("camera=(self)")
    assert "allow-same-origin" not in response.headers["Content-Security-Policy"]
    assert client.get("/gesture-sdk/v1/nar-controls.esm.js").status_code == 200
    assert client.get("/gesture-sdk/v1/../../work.json").status_code == 404
    (folder / "index.html").write_bytes(source() + b"<script>steal()</script>")
    assert client.get(f"/works/{work_id}/index.html").status_code == 404
    meta["publication_status"] = "unpublished"
    (base / "work.json").write_text(json.dumps(meta))
    assert client.get(f"/works/{work_id}/index.html").status_code == 404
