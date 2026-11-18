# Gesture Interaction MVP v0.2 — integration and rollout

## Branch / schema
- Base: `main`; implementation: `feature-intersection`.
- **No new SQL tables, columns, ORM migrations, credit rules or environment variables.**
- The immutable work `index.html` carries `GestureBindings` and the fixed Bridge script. Existing ArtifactStore/Works save, version, publish and authorization code is reused.
- The single authoritative manifest is `nar_agent/gesture/manifest.v0.2.json`; the frontend build copies it into its own public assets. The NarAgent image ships the same file.

## Browser architecture
- Parent: `GesturePlayerHost` → user-click `CameraManager` → HandLandmarker → feature extraction → deterministic state machine → validated bindings → MessageChannel.
- Child: sandboxed generated HTML `window.NarInteraction` only; cannot read the camera/video/landmarks or invoke privileged parent code.
- Opaque-origin iframe keeps `sandbox=allow-scripts` (never `allow-same-origin`). A separate, randomly generated per-iframe session and increasing sequence counter guard the channel.
- Model is pinned to the versioned MediaPipe `hand_landmarker/float16/1` resource and copied to `public/gesture/` during frontend build. MediaPipe package is pinned in npm lockfile.
- Never draw hand skeleton; 15 Hz max inference target (independent of rendering); WebGL GPU initialization falls back to CPU.
- No gesture declaration means no manifest request, no MediaPipe import and no camera prompt.

## NarAgent authoring contract
For a gesture request, use `get_gesture_manifest()`; write standalone HTML with mouse/touch controls and `window.NarInteraction` action handlers; submit JSON bindings through `validate_gesture_working_html()`. The tool owns HTML Bridge injection and reuses the existing Sandbox verification. On revisions, preserve original interface and re-validate the bindings.

To support dwell click, `NarInteraction.hover(event)` **must return `true` only when the pointer is over an interactive target**; if false/undefined, dwell click is suppressed. `click(event)` and `swipe(event)` must be idempotent from the learner's perspective.

## Testing
- Python: `cd nar_agent && uv run python -m pytest -q tests/test_gesture_composer.py tests/test_html_builder.py`.
- Frontend: `cd forge_frontend_next && npm ci && npx tsc --noEmit --incremental false`.
- Deterministic state tests: `node tests/gesture-runtime.test.cjs` (after frontend npm ci).
- Browser smoke: sandbox `browser-check.mjs` invokes declared NarInteraction methods and fails on missing functions.
- Build/asset check: `cd forge_frontend_next && npm run build` copies fixed manifest/WASM and downloads the versioned hand model.
- Manual acceptance required: Chrome/Edge desktop, Android Chrome, iOS Safari (or visible unsupported hint). Validate camera close/page hide, denied permissions, orientation, latency and actual four gesture poses.
- Semantic assertions of real object state require template-specific probes. Generic function calls only validate availability/no-exception and **do not prove a scene visibly changed**.

## Known MVP limitations
- No offline standalone gesture controls after downloading index.html outside NarrativeOS.
- One hand only; no two-hand zoom or model retraining.
- Real-device calibration/performance and accessible visual mouse/touch fallbacks must be checked before production.
