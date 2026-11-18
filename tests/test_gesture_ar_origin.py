"""Runtime Bridge safety contract; no privileged camera work iframe."""
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def read(path): return (ROOT/path).read_text(encoding="utf-8")

def test_camera_only_in_trusted_host():
    host=read("forge_frontend_next/components/gesture/gesture-work-host.tsx")
    runtime=read("forge_frontend_next/lib/gesture-bridge/runtime.ts")
    player=read("forge_frontend_next/app/practice/works/[workId]/page.tsx")
    preview=read("forge_frontend_next/app/practice/animation-preview.tsx")
    assert 'sandbox="allow-scripts"' in host
    assert 'allow="fullscreen"' in host
    assert "allow-same-origin" not in host + player
    assert 'allow="camera' not in host + player
    assert "ar.narrativeos.cn" not in host + player
    assert "createGestureRuntime" in host
    assert "GestureWorkHost" in preview and "GestureWorkHost" in player
    assert "createHands" in runtime
    assert "getUserMedia" not in read("nar_agent/templates/gesture-cards/index.html")

def test_capabilities_not_privilege():
    config=read("forge_frontend_next/next.config.mjs")
    assert "camera=(self)" in config
    assert "ar.narrativeos.cn" not in config
    bootstrap=read("forge_frontend_next/lib/gesture-bridge/bridge-bootstrap.ts")
    assert "event.source!==window.parent" in bootstrap
    assert "event.origin!==origin" in bootstrap
    assert 'MessageChannel' in read("forge_frontend_next/components/gesture/gesture-work-host.tsx")
    assert "getUserMedia" not in bootstrap
    assert "allow-same-origin" not in bootstrap

def test_no_old_scheme_a_runtime_deployment():
    docker=read("docker/frontend.Dockerfile")
    assert "COPY gesture_sdk" in docker
    assert "public/gesture-sdk/v1" in docker
    backend=read("docker/backend.Dockerfile")
    assert "gesture_sdk/review.py" not in backend
    build=read("gesture_sdk/build.mjs")
    assert "MODEL_SHA256" in build
    assert "nar-controls.esm.js" not in build

def test_generated_template_has_bridge_and_fallback():
    src=read("nar_agent/templates/gesture-cards/index.html")
    assert 'data-nar-gesture="v1"' in src
    assert "window.NarrativeGesture" in src
    assert "card.addEventListener('pointerdown'" in src
    assert "getUserMedia" not in src
    assert "import('/gesture-sdk" not in src
    assert "ar.narrativeos.cn" not in src
    assert "data-gesture-dwell" in src
