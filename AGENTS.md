# AGENTS.md

## Cursor Cloud specific instructions

### Repository overview

This is the **WebGAL Engine** (v4.6.0) — a web-based visual novel runtime built with React 17 + TypeScript + PixiJS + Vite 5. It renders and plays interactive fiction games in the browser.

### Key commands

| Task | Command |
|------|---------|
| Dev server | `npm run dev` (port 3000) |
| Build | `npm run build` |
| Type check | `npx tsc --noEmit` |
| Lint | `ESLINT_USE_FLAT_CONFIG=false npx eslint "src/**"` |

### Important notes

- **Missing dependency**: `webgal-parser` is not listed in `package.json` but is required. It must be installed separately via `npm install webgal-parser --legacy-peer-deps`.
- **npm install requires `--legacy-peer-deps`**: The `eslint-config-alloy` package has peer dependency conflicts with `@typescript-eslint/parser` v8. Always use `npm install --legacy-peer-deps`.
- **ESLint**: The project uses `.eslintrc.js` (legacy format) but ships with ESLint 9. You must set `ESLINT_USE_FLAT_CONFIG=false` to use the legacy config. Additionally, the `alloy/typescript` config enables type-checked rules that require `parserOptions.project` which is not configured — ESLint will error on type-checked rules. Basic syntax/style linting still works.
- **TypeScript check passes cleanly** once `webgal-parser` is installed.
- **Sass deprecation warnings** during build are expected (legacy JS API, @import rules) — they do not affect the build output.
- **Game assets**: `public/game/` contains sample game scenes, backgrounds, BGM, and figures for development testing.
