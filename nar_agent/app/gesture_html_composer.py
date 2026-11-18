"""Validated GestureBindings and a fixed, data-only iframe bridge.

No camera, model, threshold or privileged API is injected into generated HTML.
"""
import json
import re
from pathlib import Path

MANIFEST_PATH = Path(__file__).resolve().parents[1] / "gesture" / "manifest.v0.2.json"
PROTOCOL = "nar.gesture/0.2"
ACTION_FIELDS = {
    "rotate": {"dx", "dy"}, "grab": {"x", "y"}, "drag": {"dx", "dy"},
    "pan": {"dx", "dy"}, "hover": {"x", "y"}, "click": {"x", "y"},
    "swipe": {"direction"}, "select": {"x", "y"}, "reset": set(),
}
# This code is trusted application code. The LLM may only choose data bindings.
BRIDGE_SOURCE = r"""(function () {
"use strict";
const protocol = "nar.gesture/0.2";
const configNode = document.getElementById("nar-gesture-bindings");
if (!configNode || window.parent === window) return;
let config;
try { config = JSON.parse(configNode.textContent); } catch (_) { return; }
if (!config || config.schemaVersion !== "0.2.0" || !Array.isArray(config.bindings)) return;
const allowed = new Set(["rotate","grab","drag","pan","hover","click","swipe","select","reset"]);
const phases = new Set(["start","move","end","click","swipe","trigger"]);
let port = null, session = null, lastSeq = -1;
window.addEventListener("message", function (e) {
  if (e.source !== window.parent || !e.data || e.data.protocol !== protocol || e.data.type !== "init" || !e.ports || e.ports.length !== 1 || port) return;
  if (typeof e.data.session !== "string" || !/^[0-9a-f-]{16,64}$/.test(e.data.session)) return;
  session = e.data.session;
  port = e.ports[0];
  port.onmessage = function (message) {
    const data = message.data;
    if (!data || data.protocol !== protocol || data.type !== "command" || data.session !== session ||
        !Number.isSafeInteger(data.seq) || data.seq <= lastSeq || !allowed.has(data.action) ||
        !data.event || !phases.has(data.event.phase)) return;
    if (!config.bindings.some(b => b.action === data.action && b.phases.includes(data.event.phase))) return;
    const fields = ["x","y","dx","dy"];
    if (fields.some(k => data.event[k] !== undefined && (typeof data.event[k] !== "number" || !Number.isFinite(data.event[k]) || Math.abs(data.event[k]) > 2))) return;
    if (data.event.direction !== undefined && !["left","right","up","down"].includes(data.event.direction)) return;
    const method = Object.getOwnPropertyDescriptor(window.NarInteraction || {}, data.action)?.value;
    if (typeof method !== "function") return;
    lastSeq = data.seq;
    try {
      const outcome = method.call(window.NarInteraction, data.event);
      if (data.action === "hover") port.postMessage({protocol,type:"hover",session,hasTarget: outcome === true});
    } catch (err) { console.error("NarInteraction action failed", err); }
  };
  port.start();
  port.postMessage({protocol, type:"ready", session});
}, false);
function announce() {
  if (!port) window.parent.postMessage({protocol,type:"hello",schemaVersion:"0.2.0",bindings:config.bindings},"*");
}
announce();
setTimeout(announce,300);
setTimeout(announce,1000);
})();"""


class GestureConfigError(ValueError):
    pass


def get_manifest() -> dict:
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if data.get("schemaVersion") != "0.2.0":
        raise GestureConfigError("Unsupported gesture manifest version")
    return data


def validate_bindings(raw: str | dict) -> dict:
    if isinstance(raw, str):
        if len(raw.encode("utf-8")) > 8192:
            raise GestureConfigError("GestureBindings too large")
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise GestureConfigError("GestureBindings is not valid JSON") from exc
    if not isinstance(raw, dict) or set(raw) != {"schemaVersion", "bindings"} or raw["schemaVersion"] != "0.2.0":
        raise GestureConfigError("Unsupported GestureBindings schema")
    bindings = raw["bindings"]
    if not isinstance(bindings, list) or not 1 <= len(bindings) <= 12:
        raise GestureConfigError("Expect 1..12 gesture bindings")
    gestures = {g["id"]: g for g in get_manifest()["gestures"]}
    validated, seen = [], set()
    for b in bindings:
        if not isinstance(b, dict) or set(b) != {"gesture", "phases", "action"}:
            raise GestureConfigError("Unexpected binding fields")
        gesture = gestures.get(b["gesture"]) if isinstance(b["gesture"], str) else None
        action, phases = b["action"], b["phases"]
        if gesture is None or not isinstance(action, str) or action not in ACTION_FIELDS or action not in gesture["suggestedActions"]:
            raise GestureConfigError("Unsupported gesture/action")
        if not isinstance(phases, list) or not phases or len(phases) > 6 or not all(isinstance(p, str) and p in gesture["events"] for p in phases):
            raise GestureConfigError("Unsupported gesture phase")
        if len(set(phases)) != len(phases):
            raise GestureConfigError("Duplicate phases")
        if action == "reset" and phases != ["trigger"]:
            raise GestureConfigError("Reset requires trigger")
        if action == "swipe" and "swipe" not in phases:
            raise GestureConfigError("Swipe requires swipe phase")
        if action == "click" and "click" not in phases:
            raise GestureConfigError("Click requires click phase")
        for phase in phases:
            if phase in ("move", "click", "swipe", "trigger") and not ACTION_FIELDS[action].issubset(set(gesture["outputs"])):
                raise GestureConfigError("Action parameters incompatible with gesture outputs")
            key = (gesture["id"], phase)
            if key in seen:
                raise GestureConfigError("Gesture phase already assigned")
            seen.add(key)
        validated.append({"gesture": gesture["id"], "phases": list(phases), "action": action})
    return {"schemaVersion": "0.2.0", "bindings": validated}


def _encoded_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def compose_gesture_html(html: str, bindings: str | dict) -> str:
    if re.search(r'id\s*=\s*["\']nar-gesture-(?:bindings|bridge)["\']', html, re.I):
        raise GestureConfigError("Managed gesture bridge already exists; edit original source instead")
    if not re.search(r"</body\s*>", html, re.I):
        raise GestureConfigError("Complete HTML document required")
    config = validate_bindings(bindings)
    if "NarInteraction" not in html:
        raise GestureConfigError("Define window.NarInteraction before enabling gestures")
    injected = ('<script id="nar-gesture-bindings" type="application/json">' +
                _encoded_json(config) + '</script><script id="nar-gesture-bridge">' +
                BRIDGE_SOURCE + '</script>')
    result = re.sub(r"</body\s*>", lambda match: injected + match.group(), html, count=1, flags=re.I)
    if len(result.encode("utf-8")) > 96000:
        raise GestureConfigError("Composed HTML exceeds 96KB")
    return result


def inspect_gesture_html(html: str) -> dict | None:
    """Reject forged or tampered managed code. Unmarked HTML is ordinary HTML."""
    match = re.search(r'<script id="nar-gesture-bindings" type="application/json">([^<]*)</script><script id="nar-gesture-bridge">([\s\S]*?)</script>', html)
    if match is None:
        if "nar-gesture-bindings" in html or "nar-gesture-bridge" in html:
            raise GestureConfigError("Malformed managed gesture markup")
        return None
    if match.group(2) != BRIDGE_SOURCE or html.count('id="nar-gesture-bindings"') != 1:
        raise GestureConfigError("Gesture bridge has been modified")
    try:
        config = validate_bindings(json.loads(match.group(1)))
    except (ValueError, TypeError) as exc:
        raise GestureConfigError("Invalid embedded GestureBindings") from exc
    return config
