# WebGAL Backend Contracts

This directory contains the structured LLM contract files used by the backend.

- `openai-tools.json`: source function/tool definitions.
- `schemas/*.schema.json`: validation schemas for structured LLM artifacts.

`webgal_backend.llm.OpenAIFunctionClient` loads `openai-tools.json` directly and inlines local schema references in memory. No generated `openai-tools.built.json` file is required.

Current structured tools:

- `emit_narrative_plan`
- `emit_asset_manifest`
