"""Trusted execution broker. Only this service sees Docker, never the model.

No host mounts or caller-supplied commands/images: each invocation gets a fresh
network-disabled container. A Docker socket grants host-level authority; deploy
this small service privately and protect its independent bearer credential.
"""
import base64
import io
import json
import logging
import os
import secrets
import tarfile
import threading
import uuid

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

app = FastAPI(title="NarAgent execution broker")
logger = logging.getLogger(__name__)
slot = threading.Lock()


class BuildInput(BaseModel):
    model_config = {"extra": "forbid"}
    source: str = Field(min_length=1, max_length=96000)


def extract_file(container, path: str, limit: int) -> bytes:
    stream, _ = container.get_archive(path)
    raw = bytearray()
    for chunk in stream:
        raw.extend(chunk)
        if len(raw) > limit + 65536:
            raise ValueError("Artifact archive exceeds size limit")
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        members = archive.getmembers()
        if len(members) != 1 or not members[0].isfile() or members[0].size > limit:
            raise ValueError("Expected one bounded regular file")
        return archive.extractfile(members[0]).read()


def execute(source: str):
    import docker
    client = docker.from_env(timeout=15)
    container = None
    try:
        image = os.environ["NAR_SANDBOX_IMAGE"]
        # Resolve an already-pulled immutable image ID; no image selection by model.
        image_id = client.images.get(image).id
        container = client.containers.run(
            image_id, command=[base64.b64encode(source.encode()).decode()], detach=True,
            name="nar-sandbox-" + uuid.uuid4().hex,
            network_mode="none", read_only=True, user="0:0",
            cap_drop=["ALL"], cap_add=["SETUID", "SETGID"], security_opt=["no-new-privileges:true"],
            mem_limit="2g", memswap_limit="2g", nano_cpus=1000000000, pids_limit=128,
            tmpfs={"/work": "rw,nosuid,noexec,size=64m,mode=777", "/results": "rw,nosuid,noexec,size=16m,mode=700", "/tmp": "rw,nosuid,size=256m,mode=1777"},
            shm_size="128m", log_config=docker.types.LogConfig(type="json-file", config={"max-size": "1m", "max-file": "1"}),
            labels={"narrativeos.role": "animation-sandbox"},
        )
        # tmpfs disappears when a container stops: copy results while supervisor waits.
        import time
        deadline = time.monotonic() + 110
        while time.monotonic() < deadline:
            container.reload()
            if container.status != "running":
                raise RuntimeError("Sandbox exited before completing report")
            try:
                report = json.loads(extract_file(container, "/results/report.json", 128000))
                break
            except docker.errors.NotFound:
                time.sleep(.3)
        else:
            raise TimeoutError("Sandbox time limit")
        result = {"report": report}
        if report.get("passed"):
            for name, limit in [("index.html", 2000000), ("preview.png", 3000000), ("mobile.png", 3000000)]:
                result[name] = base64.b64encode(extract_file(container, "/results/" + name, limit)).decode()
        return result
    finally:
        try:
            if container is not None:
                container.remove(force=True)
        finally:
            client.close()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/execute")
async def build(payload: BuildInput, authorization: str = Header(default="")):
    token = os.getenv("NAR_EXECUTION_TOKEN", "")
    if len(token) < 32 or token.startswith("replace-with-") or not secrets.compare_digest(authorization.encode(), ("Bearer " + token).encode()):
        raise HTTPException(401, "Invalid execution credentials")
    if len(payload.source.encode()) > 96000:
        raise HTTPException(422, "Source too large")
    if not slot.acquire(blocking=False):
        raise HTTPException(429, "Execution capacity reached")
    try:
        return await run_in_threadpool(execute, payload.source)
    except Exception as error:
        logger.warning("Sandbox execution failed: %s", type(error).__name__)
        raise HTTPException(502, "Sandbox execution failed; inspect broker logs and runtime image") from None
    finally:
        slot.release()


@app.get("/ready")
def ready():
    import docker
    token = os.getenv("NAR_EXECUTION_TOKEN", "")
    if len(token) < 32 or token.startswith("replace-with-"):
        raise HTTPException(503, "Execution token not configured")
    try:
        with docker.from_env(timeout=3) as client:
            client.ping()
            client.images.get(os.environ["NAR_SANDBOX_IMAGE"])
    except Exception:
        raise HTTPException(503, "Docker runtime image not ready") from None
    return {"status": "ready"}
