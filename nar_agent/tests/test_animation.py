import base64
import hashlib
import io
import json
import os
import tarfile
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.artifacts import ArtifactStore
from app.config import Settings
from app.main import create_app
from sandbox import broker


def test_real_animation_graph_build_tool(monkeypatch, tmp_path):
    import asyncio
    import httpx
    import agents.animation as module
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    class Model(GenericFakeChatModel):
        def bind_tools(self, tools, **kwargs): return self
    model = Model(messages=iter([
        AIMessage(content="", tool_calls=[{"name": "read_file", "args": {"file_path": "/skills/anatomy/SKILL.md"}, "id": "read"}]),
        AIMessage(content="", tool_calls=[{"name": "build_animation", "args": {"source": "// complete test builder"}, "id": "build"}]),
        AIMessage(content="请点击开关操作演示。"),
    ]))
    original = httpx.AsyncClient
    def respond(request):
        assert json.loads(request.content)["source"] == "// complete test builder"
        assert request.headers["authorization"].startswith("Bearer ")
        return httpx.Response(200, json=payload())
    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **kw: original(**kw, transport=httpx.MockTransport(respond)))
    config = Settings(_env_file=None, artifact_dir=str(tmp_path), execution_token="x" * 40)
    state = {}
    graph = module.build_animation_agent(config, "owner", state, ArtifactStore(str(tmp_path)), model=model)
    result = asyncio.run(graph.ainvoke(module.animation_state("制作电路", []), config={"recursion_limit": 40}))
    assert state["artifact_id"] and state["attempts"] == 1
    assert result["messages"][-1].content == "请点击开关操作演示。"


def payload():
    return {"report": {"passed": True}, **{name: base64.b64encode(data).decode() for name, data in {"index.html": b'<svg></svg><button>toggle</button>', "preview.png": b'png', "mobile.png": b'png'}.items()}}


def test_private_immutable_artifacts(tmp_path):
    store = ArtifactStore(str(tmp_path))
    identifier = store.save("owner-a", payload(), "source")
    assert store.read("owner-a", identifier, "index.html").startswith(b"<svg")
    for owner, key, name in [("owner-b", identifier, "index.html"), ("owner-a", "../escape", "index.html"), ("owner-a", identifier, "metadata.json")]:
        with pytest.raises(FileNotFoundError):
            store.read(owner, key, name)


def test_vendor_integrity():
    root = Path(__file__).resolve().parents[1] / "skills"
    lock = json.loads((root / "anatomy.lock.json").read_text())
    assert len(lock["commit"]) == 40
    for filename, digest in lock["files"].items():
        assert hashlib.sha256((root / "anatomy" / filename).read_bytes()).hexdigest() == digest, filename
    assert "MIT License" in (root / "anatomy/LICENSE").read_text()


def archive(data, symlink=False):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as tar:
        member = tarfile.TarInfo("index.html")
        if symlink:
            member.type = tarfile.SYMTYPE; member.linkname = "/etc/passwd"
            tar.addfile(member)
        else:
            member.size = len(data); tar.addfile(member, io.BytesIO(data))
    return output.getvalue()


def test_archive_rejects_symlinks_and_oversized_objects():
    class Container:
        def get_archive(self, path):
            return [archive(b"x", symlink=True)], {}
    with pytest.raises(ValueError):
        broker.extract_file(Container(), "/work/index.html", 100)


def test_execution_cannot_select_commands_mounts_or_network(monkeypatch):
    import docker
    captured = {}
    class Container:
        status = "running"
        def reload(self): pass
        def get_archive(self, path):
            data = json.dumps({"passed": False, "error": "test build failure"}).encode()
            return [archive(data)], {}
        def remove(self, **kw): captured["removed"] = kw
    class Images:
        def get(self, image): return type("Image", (), {"id": "sha256:pinned"})()
    class Containers:
        def run(self, image, **kw): captured.update(kw); return Container()
    class Client:
        images = Images(); containers = Containers()
        def close(self): captured["closed"] = True
    monkeypatch.setattr(docker, "from_env", lambda **kw: Client())
    monkeypatch.setenv("NAR_SANDBOX_IMAGE", "test-runtime:locked")
    assert broker.execute("console.log('test')")["report"]["passed"] is False
    assert captured["network_mode"] == "none"
    assert captured["read_only"] and captured["cap_drop"] == ["ALL"]
    assert captured["user"] == "0:0" and captured["cap_add"] == ["SETUID", "SETGID"] and "volumes" not in captured
    assert "environment" not in captured and captured["pids_limit"] == 128
    assert captured["removed"] == {"force": True} and captured["closed"]


def test_animation_status_and_artifact_owner(tmp_path):
    token = "test-" + "x" * 40
    config = Settings(_env_file=None, service_token=token, api_key="fake", animation_enabled=True, execution_token=token, artifact_dir=str(tmp_path))
    class Graph:
        def __init__(self, state, store, owner): self.state, self.store, self.owner = state, store, owner
        async def ainvoke(self, *args, **kw):
            self.state["artifact_id"] = self.store.save(self.owner, payload(), "source")
            return {"messages": [AIMessage(content="可操作演示已生成") ]}
    app = create_app(config, animation_factory=lambda settings, owner, state, store: Graph(state, store, owner))
    headers = {"Authorization": "Bearer " + token, "X-User-ID": "teacher-a"}
    with TestClient(app) as client:
        response = client.post("/v1/animations", headers=headers, json={"prompt": "串联电路"})
        assert response.status_code == 202
        identifier = response.json()["id"]
        for _ in range(100):
            state = client.get("/v1/animations/" + identifier, headers=headers).json()
            if state["status"] != "RUNNING": break
            time.sleep(.01)
        assert state["status"] == "SUCCEEDED"
        url = "/v1/artifacts/" + state["artifact_id"] + "/index.html"
        artifact = client.get(url, headers=headers)
        assert artifact.status_code == 200
        assert "sandbox allow-scripts" in artifact.headers["content-security-policy"]
        other = {**headers, "X-User-ID": "teacher-b"}
        assert client.get(url, headers=other).status_code == 404
        assert client.get("/v1/animations/" + identifier, headers=other).status_code == 404


@pytest.mark.skipif(os.getenv("NAR_TEST_DOCKER") != "1", reason="Requires Docker; CI explicitly enables real sandbox smoke")
def test_real_docker_anatomy_build():
    root = Path(__file__).resolve().parents[1] / "skills/anatomy"
    source = (root / "examples/dial-indicator/build.mjs").read_text(encoding="utf-8")
    source = source.replace('"../../kit/', '"/opt/anatomy/kit/').replace('"../../scripts/', '"/opt/anatomy/scripts/')
    source = source.replace('join(HERE, theme === "light" ? "dial-indicator-light.html" : "dial-indicator.html")', '"/work/index.html"')
    result = broker.execute(source)
    assert result["report"]["passed"], result["report"]
    assert b"<svg" in base64.b64decode(result["index.html"])
    assert base64.b64decode(result["preview.png"]).startswith(b"\x89PNG")
