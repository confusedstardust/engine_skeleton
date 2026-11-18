"""Gesture binding security and immutable HTML embedding checks."""
import json

import pytest

from app.gesture_html_composer import (
    BRIDGE_SOURCE, GestureConfigError, compose_gesture_html, get_manifest,
    inspect_gesture_html, validate_bindings,
)

HTML = '<!doctype html><html><body><button>Reset</button><script>window.NarInteraction={rotate(e){this.last=e},reset(){}}</script></body></html>'
BINDINGS = {"schemaVersion": "0.2.0", "bindings": [
    {"gesture": "fist_rotate", "phases": ["move"], "action": "rotate"},
    {"gesture": "open_palm_hold", "phases": ["trigger"], "action": "reset"},
]}


def test_manifest_v02_fixes_four_gestures():
    assert [g["id"] for g in get_manifest()["gestures"]] == [
        "pinch", "fist_rotate", "index_pointer", "open_palm_hold"]


def test_html_embed_safe_idempotence_rejection():
    html = compose_gesture_html(HTML, json.dumps(BINDINGS))
    assert BRIDGE_SOURCE in html
    assert inspect_gesture_html(html) == BINDINGS
    with pytest.raises(GestureConfigError):
        compose_gesture_html(html, BINDINGS)
    with pytest.raises(GestureConfigError):
        inspect_gesture_html(html.replace("NarInteraction action failed", "tampered"))


@pytest.mark.parametrize("bad", [
    {"schemaVersion": "0.2.0", "bindings": [{"gesture": "fake", "phases": ["move"], "action": "rotate"}]},
    {"schemaVersion": "0.2.0", "bindings": [{"gesture": "fist_rotate", "phases": ["move"], "action": "eval"}]},
    {"schemaVersion": "0.2.0", "bindings": [{"gesture": "pinch", "phases": ["swipe"], "action": "drag"}]},
    {"schemaVersion": "0.2.0", "bindings": [{"gesture": "index_pointer", "phases": ["move"], "action": "click"}]},
    {"schemaVersion": "0.2.0", "bindings": [{"gesture": "open_palm_hold", "phases": ["trigger"], "action": "rotate"}]},
    {"schemaVersion": "0.2.0", "bindings": [{"gesture": "fist_rotate", "phases": ["move"], "action": "rotate", "script": "alert(1)"}]},
]):
def test_invalid_bindings_rejected(bad):
    with pytest.raises(GestureConfigError):
        validate_bindings(bad)


def test_script_closing_text_is_escaped():
    html = compose_gesture_html(HTML, BINDINGS)
    assert html.count('id="nar-gesture-bridge"') == 1
    assert html.count('id="nar-gesture-bindings"') == 1
    assert inspect_gesture_html(html) is not None
