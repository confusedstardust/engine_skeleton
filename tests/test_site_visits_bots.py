from contextlib import contextmanager
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import webgal_backend.site_visits as visits


def test_robots_are_excluded_before_uv_write_through_direct_and_proxy(monkeypatch):
    writes = []
    class Cursor:
        def execute(self, sql, params):
            writes.append((sql, params))
    @contextmanager
    def fake_db():
        yield Cursor()
    monkeypatch.setattr(visits, "database_transaction", fake_db)
    app = FastAPI()
    app.include_router(visits.router)
    reverse_proxy = FastAPI()
    reverse_proxy.mount("/api/forge", app)
    visitor = {"visitor_id": str(uuid4())}
    for client, path in [(TestClient(app), "/play/_telemetry/visit"),
                         (TestClient(reverse_proxy), "/api/forge/play/_telemetry/visit")]:
        for bot in (
            "GoogleOther", "Googlebot/2.1", "Mozilla/5.0 (compatible; ReflectionBot)",
            "Mozilla/5.0 (compatible; Baiduspider/2.0)",
            "Baiduspider-image", "https://www.baidu.com/search/spider.html",
        ):
            response = client.post(path, json=visitor, headers={"User-Agent": bot})
            assert response.status_code == 204
        assert client.post(path, json=visitor,
                           headers={"User-Agent": "Mozilla/5.0 Chrome/157.0 Safari/537.36"}).status_code == 204
        assert client.post(path, json=visitor,
                           headers={"User-Agent": "Baidu Browser Android"}).status_code == 204
    assert len(writes) == 4  # two ordinary browsers, two ingress paths
    assert all("site_daily_visitors" in sql for sql, _ in writes)


def test_crawlers_can_still_fetch_the_visitor_script():
    app = FastAPI()
    app.include_router(visits.router)
    response = TestClient(app).get("/play/_telemetry/visitor.js",
                                   headers={"User-Agent": "Googlebot/2.1"})
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
