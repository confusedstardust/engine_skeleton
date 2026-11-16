# NarAgent Billing V2 — integration gates and rollout status

Updated 2026-11-16. Target `feature/quiz-card`. This document **does not** authorize
changing user balances. Follow the full source plan `NarrativeOS_NarAgent_Billing_V2_Implementation_Plan.md`
(available in the planning conversation).

## Current integration boundary

| Component | Current state |
|---|---|
| Additive MySQL migration | `credit_system/migrations/006_nar_billing_v2.sql`, repository only |
| Task/call quote schema | `webgal_backend/nar_metering_v2.py`, `nar_reconcile_v2.py` |
| Per-call capture | NarAgent + Forge, **shadow off by default** |
| Escalating credit hold | `CreditService.extend_reservation`, **not called by live Agent** |
| Legacy V1 billing | **Unchanged** except frozen task price snapshot |
| Live V2 settlement | **Not wired / off** |
| Budget approval / resume UI | **Not implemented** |
| Provider-bill reconciliation | **Not implemented** |

## Feature flags: MUST remain off until every gate passes

```dotenv
NAR_BILLING_V2_METER_SHADOW_PERCENT=0
NAR_BILLING_V2_LIVE_PERCENT=0
NAR_BILLING_V2_BUDGET_ENFORCE=false
NAR_BILLING_V2_CHARGE_INTENT=false
```

These do **not** replace the independent V2 semantic-intent gates. The existing
`NAR_INTENT_V2_LIVE_PERCENT` can remain at its independent default (zero).

## Manual schema preparation

Before internal-only shadow collection, review and back up the correct
development MySQL database, then apply migration 006 once. It creates
`nar_usage_events`, `nar_task_billing`, `nar_reservation_extensions`
and `nar_price_catalog`. CI currently runs the migration only against disposable
MySQL. Do **not** point tests, samples or experimental jobs at production. Never
replay old tasks to charge historical users.

No production schema migration is performed automatically by a merge/deployment.
The new capture code is not made live by applying the migration.

## Missing critical path before user billing activation

1. Durable `billing_session_id` and provisional Turn must be created BEFORE
   formal intent calls. Existing `submit_turn` performs auto routing first.
2. Authenticate actual, explicit user budget limit. Authorize and freeze enough
   before the FIRST provider call (including formal intent). For every future
   paid model/tool call, strictly gate on remaining budget and atomically call
   `extend_reservation` before sending; on shortage, stop and offer a reversible
   approval/continuation UI. Never charge above the approved limit.
3. Commit each per-call usage event once. Stage eligibility: formal intent joins
   the completed paid session; pure clarification and shadow are company-funded.
   Provider-unknown usage enters reconciliation. No fabricated zero usage.
4. Create a durable idempotent task finalizer that validates event completeness,
   snapshot price, wallet reservation and billed-session ownership; capture
   exactly once, or release/mark NEEDS_REVIEW with an explicit policy.
5. Reconcile with actual provider invoice records, include image/TTS/external
   tool cost where supported, and add admin usage/cost/margin reports.
6. Validate real provider streams, interrupted requests, webhook/worker retries,
   two-account isolation, low-balance escalation, mid-run price change, lost
   callback and model timeout. Confirm no overauthorized charge and no duplicate
   capture, then opt in testers only before any general rollout.

## Operational warning

The legacy NarAgent path still charges
`min(measured, initial_20_credit_reservation)`. This **undercharges** tasks
that run beyond 20 credits, but intentionally prevents over-capture while
up-front authorization is missing. Do **not** delete the clamp before step 2.

Do **not** describe the 35-credit database extension unit/integration test as
proof that a live, unmodified NarAgent task now charges 35. The test uses an
explicit trusted extension before settlement; production routing doesn't.

## Tests and reconciliation

- `tests/test_nar_metering_v2.py`: cached input disjoint, no reasoning double
  counting, Decimal user quote, provider cost separate.
- `tests/test_nar_billing_v2_mysql.py`: immutable event deduplication and
  real disposable-MySQL reservation extension → 35-credit capture.
- `nar_agent/tests/test_metering.py`: callback deduplication, known/unknown
  status and prompt-free event capture.
- `tests/test_nar_reconcile_v2.py`: final quote rejects uncertain usage,
  duplicate callbacks, cross-session events and overbudget invoices.

Visible user UI remains the unified golden credit/time timeline. Do not add a
token-usage card or download-HTML button as part of billing rollout.
