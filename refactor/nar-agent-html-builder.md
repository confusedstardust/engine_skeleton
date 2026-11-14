# NarAgent L1/L2 HTML Builder — implementation decision & verification

## Scope

This change builds on the existing Python NarAgent, sandbox broker, Chromium CDP
smoke checks, ArtifactStore, Forge SSO gateway and Next /practice entry.
No host shell, user-supplied Docker mount, arbitrary backend service, user data DB,
automatic publication or production credential exposure is added.

## Integration map

| Existing component | Change |
|---|---|
| agents/teaching.py | Preserved, chat remains a separate explicit action |
| agents/animation.py | Preserved, existing isolation and animation build unchanged |
| agents/html_builder.py | New tool-using HTML creation, template selection, edit tool and repair loop |
| app/template_catalog.py | New reviewed-template registry, schema validation and safe JSON injection |
| templates/recitation-cards | First versioned interactive flashcard template |
| skills/html-builder | Agent guidance, distinct from executable templates |
| sandbox/broker.py + run.mjs | Add 'html' execution mode to existing isolated Chromium broker |
| app/artifacts.py | Immutable revisions with kind, parent id, owner validation |
| app/main.py | Explicitly opt-in async HTML create/status routes |
| webgal_backend/nar_agent_routes.py | Existing SSO-protected proxy extended to HTML tasks |
| /practice | Explicit create / revise controls, preview and HTML download |

## Task state and revisions

- POST /v1/html accepts prompt, bounded user/assistant history, optional parent_artifact_id.
- Owner identity is asserted by the trusted Forge backend (never the browser).
- Owner and parent type are checked before allocating a run; foreign parents return 404.
- A successful browser-verified build creates a new immutable artifact with owner, kind,
  timestamp and parent_id metadata.
- Existing source is read only via owner-authorized artifact, or a unique-span edit tool.
- In-memory asynchronous progress is non-durable. Restarts drop outstanding run status.

## Template specification

First template ID: recitation-cards, version 1.0.0.
Manifest is read from bundled trusted files; arbitrary file paths are rejected.
Inputs: title and 1–40 cards with exact question/answer fields.
JSON inserted into nonexecuting application/json script tag with special characters
escaped; JS renders values via textContent. No user-controlled HTML is evaluated
in the template pathway.

Follow-ups: move to JSON Schema per template, add quiz / relationship / simulation
templates and shared declarative component contracts. Avoid duplicating mutable
business logic in the Agent prompt.

## Browser and security properties

- Existing network disabled Docker execution sandbox, no user selected image/mounts.
- HTML mode writes index.html directly, never executes its source in Node.
- Chromium checks console/runtime exceptions, controls, offline external resources,
  screenshots and 390px overflow.
- Browser still executes JS (in isolated disposable container); output preview has
  iframe sandbox + restrictive CSP and no same-origin.
- Preflight regexes are defensive hints, not trusted sanitization. Strict auth, CSP,
  container isolation, and server-side limits remain the security boundaries.
- Current CDP smoke does not fully assert every interaction or teaching correctness;
  next PR should add template-specific Playwright test contracts and screenshot review.

## Compatibility / limitations

The existing /v1/animations path, input contract and storage format remain compatible.
HTML builder opt-in flag defaults false; Docker overlay turns it on when provisioned.
This first PR does not automate routing from freeform chat to a builder; the user
explicitly selects '生成 HTML' or '修改当前作品'. This preserves stable chat behavior.
No queue, billing, OSS or production readiness is claimed. A future iteration should
persist job state, accounting and artifact metadata centrally with transactional
idempotency before expanding beyond controlled beta.

## Verification checklist

- [ ] Python unit/service tests pass (local or GitHub Actions)
- [ ] Real Docker Chromium HTML smoke passes in CI
- [ ] Original anatomy animation Docker smoke passes in CI
- [ ] Forge gateway auth and owner mismatch tests pass
- [ ] Next TypeScript check passes
- [ ] Logged-in browser can generate, preview, download, revise and recover errors
- [ ] Deploy/Feishu documentation synchronization (pending separately)

Production release requires finishing the items above and reviewing prompt/tool
budgets, concurrency, local storage retention, and preview CSP.

## Repair draft semantics

The Agent keeps the latest submitted HTML as an in-memory **working draft**, even when
Chromium checks fail. `read_working_html`, `inspect_working_html`, and
`replace_working_html` operate on that latest draft. Only successful validated builds
create immutable artifacts; failed drafts are not published or saved as user revisions.
This allows bounded repair without re-sending an entire generated L2 document.
