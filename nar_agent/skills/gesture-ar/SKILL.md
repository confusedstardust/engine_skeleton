---
name: gesture-ar
description: Generate NarrativeOS reviewed AR gesture learning cards with the in-frame hand-gesture-kit SDK.
---

# NarrativeOS AR Hand Gestures (方案 A)

For camera gesture requests, call `search_html_templates("手势")` then `render_html_template("gesture-cards", config_json)` with exactly {title,cards:[{question,answer}]} (1–40 cards). This is the **only** camera-capable template approved by the v1 server; arbitrary generated JS never gains camera permissions.

The reviewed template loads `/gesture-sdk/v1/nar-controls.esm.js` **from the work origin**, which imports the pinned `hand-gesture-kit.esm.js`. Each work uses its own `createHands()` instance, `numHands:1`, `assetBase:'/gesture-sdk/v1/'`, `onFrame`, and `engine.on('fist')`. Never invent upstream `pause()/dispose()/fist_rotate` APIs; `fist_rotate` etc are the platform adapter's actions, not SDK events.

Manifest v1: `pinch-drag` (pinch hysteresis 0.72/0.36; index tip moves object), `fist-rotate` (fist + center x delta), `index-dwell` (point + hit-test + 700ms dwell), `open-reset` (open held 900ms). There is always mouse/touch/keyboard fallback. Buttons explicitly start and stop the camera, with cleanup on pagehide/hidden and new instance on restart. No webcam/video/landmark exfiltration; no CDN, fetch or arbitrary external scripts.

**Verification tiers**: sandbox Chromium verifies offline fallback and DOM controls only; it cannot verify live MediaPipe. Server performs byte-identical reviewed template validation before admitting content to the isolated origin. Real camera, gesture hit tests, iOS Safari and Permissions Policy require browser tests on the deployed independent HTTPS origin. Main-site srcdoc and ordinary iframe previews must NEVER gain allow-same-origin plus camera.
