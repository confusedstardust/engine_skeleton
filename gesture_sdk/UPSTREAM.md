# Vendored hand-gesture-kit

Upstream: https://github.com/abouchedidxcode/open-source-hands
Pinned commit: `dd79fb7b3a9d2e9868e433611e6b8737dfca3936` (2026-11-18 integration snapshot)
Package: hand-gesture-kit 0.1.0, MIT (see LICENSE.upstream).
MediaPipe Tasks Vision is pinned to 1.1.0; consult its separate license.
The TypeScript in `src/kit/` is copied unmodified from that commit.

Run `npm install && npm run build` in this directory (build host requires network to download the fixed Google model). Output `dist/gesture-sdk/v1/` is served from the **separate artifact origin**. Do not copy it under the main application's authenticated origin.

The model is currently fetched from a fixed Google URL at build time; before production promotion, record and pin the binary SHA-256 in the release manifest and verify it at build. This is not a claim of reproducible binary assets yet.
