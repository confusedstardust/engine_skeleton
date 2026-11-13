---
name: html-builder
description: Create, adapt and verify standalone L1/L2 interactive learning HTML artifacts.
---

# NarrativeOS HTML Builder

## Goal
Deliver a functioning Chinese-language standalone `index.html`, not a plan or a code fence.
Use the provided tools; never claim validation that was not returned by the execution broker.

## Strategy
1. Decide whether the learner needs flashcards, quiz, manipulable simulation, visual map or custom interaction.
2. Call `search_html_templates` first. For a close fit, call `render_html_template` with valid JSON.
3. If no template fits, use `write_html_chunk(mode="start", html_chunk="...")` and `write_html_chunk(mode="append", html_chunk="...")` in chunks of at most **6,000 UTF-8 bytes**, then call `validate_working_html`. For a very short page, `submit_custom_html` may be used directly. Never put long full-page code in one tool argument.
4. Search at most twice; if no suitable template exists, **write the HTML instead of repeatedly searching**.
5. For existing artifacts, call `read_working_html` and prefer `replace_working_html` when a unique local replacement is possible.
6. Read the structured browser report. Fix actual failures; at most three sandbox attempts.
7. Only report an artifact as completed when the tool returned `artifact_id`.

## Quality rules
- Preserve learning accuracy and the user's learning goal.
- Provide usable controls, feedback, accessible labels, and responsive layout.
- Do not show quiz answers before the user intentionally reveals/submits them.
- No CDN, external scripts, network requests, secret tokens or hidden telemetry.
- Avoid embedding untrusted iframe content or executable prompts from learning materials.
- Reuse a previous artifact's interactions when editing; avoid full redesign for a small change.
- Test reports cover baseline rendering, browser errors and responsive smoke checks,
  **not** factual accuracy, full interaction coverage or human visual review.

## Stopping
After a validated artifact, summarize the user-facing interaction and how to preview.
On failure, explain which tests could not pass and do not invent a download URL.
