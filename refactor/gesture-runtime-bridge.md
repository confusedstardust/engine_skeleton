# NarrativeOS Gesture Runtime Bridge v1 — implementation and test notes
Date: 2026-11-19. Branch: `feature-ar`. Based on `NarrativeOS_Gesture_Runtime_Bridge_Implementation_v2.0.md`.
Status: **implemented in branch, not production deployed or camera-validated**.

## Trust boundaries
- Parent Next.js `GestureWorkHost` owns camera, MediaPipe `createHands`, `GestureAdapter`, and a single active tracker. No service sends camera data to the backend.
- The HTML work is `<iframe sandbox="allow-scripts" allow="fullscreen">` without `allow-same-origin` or camera delegation, even if loaded under the same HTTP host.
- Parent builds HTML from inert DOMParser, prepends CSP, then inserts the platform-owned Bootstrap first. Every iframe mount uses a CSPRNG session and dedicated MessageChannel, with protocol/session/sequence validation. Only READY/DISPOSED are accepted from the child; the work cannot invoke privileged Host RPC.
- Only semantic events pointer, pinch, rotate, swipe, reset and status cross the bridge; never video, raw landmarks, user tokens or cookies.
- Work capability `<body data-nar-gesture="v1">` is a UI flag, not a permission. Old works without it retain the former sandboxed `src` player.

## Routes and compatibility
- Uncommitted generated HTML: `AnimationPreview` -> `GestureWorkHost` -> source HTML as `srcDoc`.
- Saved/private works: existing authenticated `/works/:id/assets/:version/index.html` read by `workApi.html`; only the parent sees this text.
- Public works: existing `/public/works/:id/index.html` read under the current publication rules.
- Non-gesture works: keep their existing `src` iframe navigation to avoid changes to old HTML resource semantics.
- Parent component reused; WorkInspector never requests camera directly. Existing Artifact/Work/publication data and version authorization unchanged. No DB or required environment variables.

## SDK/assets build
`docker/frontend.Dockerfile` copies the existing fixed `gesture_sdk/src/kit`, installs its pinned package dependencies, runs `gesture_sdk/build.mjs`, verifies the SHA-256 of the Google MediaPipe `hand_landmarker.task`, then copies ESM/WASM/model to Next `public/gesture-sdk/v1`. The runtime loads assets via `withBasePath`. For local frontend development first run:
```sh
cd gesture_sdk && npm install && npm run build
mkdir -p ../forge_frontend_next/public/gesture-sdk/v1
cp -R dist/gesture-sdk/v1/. ../forge_frontend_next/public/gesture-sdk/v1/
```
The legacy `ar-player`/AR compose/deployment and child SDK loader were removed.

## Manifest and GameBindings
`gesture-bridge/manifest.ts` is the threshold source of truth. Parent adapter emits:
- pinch start/move/end with hysteresis 0.72/0.36 (drag)
- rotate deltaX [-0.1,0.1] during fist (rotate)
- pointer x/y and pose, child dwell `data-gesture-dwell` 700ms (click)
- swipe left/right in point pose over 120-650ms (paging)
- reset on open hand held 900ms (reset)
Events are in 0..1 iframe-relative coordinate space; game code maps them to DOM or Canvas local coordinates. Mouse/touch/keyboard call the same GameInput operations.

## Security and operations
- Browsers require HTTPS or localhost for `getUserMedia`. Bare remote HTTP IP may exercise only mock gestures and fallback.
- The main-site Permissions-Policy allows camera self only; generated iframe cannot request camera.
- Device loss, unmount, navigation, tab hide, pagehide and changing works stop or replace the old tracker/MessagePort.
- Any downloaded standalone HTML has no Bridge, and always needs conventional controls.
- Do not log video, landmarks or work HTML to telemetry.

## Test plan and known limitations
Automated test targets: Python safety/template tests, Node work UI tests, HTML Builder browser-check, frontend TypeScript/build and SDK fixed model hash. Browser smoke mocks should assert DOM changes, dwell/swipe and stale session; these are not substitutes for real camera tests.
**Still required before marking PR ready:** HTTPS/localhost camera permission allow/deny, live MediaPipe gestures and mirrored coordinates, private/history/public/withdrawn works, iOS Safari and Android, GPU/CPU fallback, 15-minute memory and power soak, security/CSP and reverse-proxy Permissions-Policy checks. Do not merge or deploy without user approval.
