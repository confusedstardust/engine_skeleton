# AGENTS.md

## Cursor Cloud specific instructions

### Repository overview

This is **WebGAL Forge** — a full-stack visual novel generation system that combines:
1. **WebGAL Engine** (v4.6.0) — React + TypeScript + PixiJS + Vite web-based visual novel runtime
2. **Forge Backend** — FastAPI + DeepSeek LLM pipeline for generating games from text input
3. **Asset Scripts** — Python scripts for image generation via 火山引擎 ARK API

### Key commands

| Task | Command |
|------|---------|
| Install JS deps | `npm install --legacy-peer-deps && npm install webgal-parser --legacy-peer-deps` |
| Install Python deps | `pip install -r requirements.txt` |
| Build engine | `npm run build` |
| Dev server (engine only) | `npm run dev` (port 3000) |
| Start Forge backend | `uvicorn webgal_backend.app:app --host 0.0.0.0 --port 8010` |
| Type check | `npx tsc --noEmit` |
| Lint | `ESLINT_USE_FLAT_CONFIG=false npx eslint "src/**"` |

### Important notes

- **npm install requires `--legacy-peer-deps`** due to `eslint-config-alloy` peer dep conflicts.
- **`webgal-parser`** is not in `package.json` but required — install separately.
- **The Forge backend** serves both the generation frontend (port 8010 `/`) and the game player (`/play/{job_id}/`).
- **After `npm run build`**, the `dist/` directory contains the static engine that the backend serves for game playback.
- **Environment variables** are loaded from `.env` file (copy `.env.example` as template).
- **DeepSeek API key** (`DEEPSEEK_API_KEY`) is required for the LLM generation pipeline.
- **ARK API key** (`ARK_API_KEY`) is required only if image generation is enabled.
- **Image generation model**: `doubao-seedream-4-5-251128` (configured in `asset_scripts/generate_assets.py`).
- **ESLint**: Uses legacy `.eslintrc.js` with ESLint 9 — set `ESLINT_USE_FLAT_CONFIG=false`. Type-checked rules may error due to missing `parserOptions.project`.
- **Sass deprecation warnings** during build are harmless.
