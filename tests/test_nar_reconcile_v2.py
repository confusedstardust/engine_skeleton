from decimal import Decimal
import pytest

from webgal_backend.nar_reconcile_v2 import reconcile_task_quote

OWNER, SESSION = "owner-a", "a" * 32


def event(key="a", stage="builder", billable=True, **overrides):
    row = dict(owner_user_id=OWNER, billing_session_id=SESSION,
               call_id=key, attempt_id="attempt-1", stage=stage,
               billable_to_user=billable, usage_status="REPORTED",
               input_uncached=1000, cache_read_input=10000,
               cache_write_input=0, output_total=200,
               reasoning_output=100,
               image_count=0, tts_characters=0, tool_calls=0)
    row.update(overrides)
    return row


def quote(events, *, delivered=True, final=True, authorized=20, reserved=20,
          expected=1, snapshot=None):
    return reconcile_task_quote(owner=OWNER, billing_session_id=SESSION,
        events=events, pricing_snapshot=snapshot or {},
        reserved_credits=reserved, authorized_credits=authorized,
        expected_billable_calls=expected, delivered=delivered,
        billing_session_final=final)


def test_intent_brief_and_builder_round_once_at_end():
    records = [event("i", "intent_v2", output_total=100),
               event("b", "public_brief", output_total=100),
               event("g", "builder", output_total=1200)]
    q = quote(records, expected=3)
    assert q.status == "READY"
    # each call has .2 input; total output is 1.4k -> 1.12 credits
    # .6 input + 1.12 output => 1.72 => ceil 2, not 1+1+2=4
    assert q.raw_credits == Decimal("1.72")
    assert q.credits == 2


def test_shadow_is_company_cost_never_user_charge():
    q = quote([event("shadow", "intent_shadow", False, output_total=500000),
               event("real", "builder", True)], expected=1)
    assert q.status == "READY" and q.credits == 1
    q = quote([event("shadow", "intent_shadow", True),
               event("real", "builder", True)], expected=1)
    assert q.status == "RECONCILING"


def test_no_artifact_is_free_even_if_supplier_call_is_unknown():
    q = quote([event("failed", usage_status="UNKNOWN", input_uncached=None)], delivered=False)
    assert q.status == "FREE" and q.credits == 0 and not q.can_capture


def test_unknown_usage_and_duplicate_callback_never_become_a_ready_invoice():
    incomplete = quote([event(usage_status="PARTIAL", output_total=None)])
    assert incomplete.status == "RECONCILING" and incomplete.credits is None
    repeated = quote([event("same"), event("same")], expected=2)
    assert repeated.status == "RECONCILING"
    missing = quote([event("only")], expected=2)
    assert missing.status == "RECONCILING"


def test_budget_35_requires_prior_authorization_and_hold():
    large = [event("large", input_uncached=0, output_total=43750)]
    assert quote(large, authorized=20, reserved=20).status == "OVER_BUDGET"
    assert quote(large, authorized=35, reserved=20).status == "OVER_BUDGET"
    accepted = quote(large, authorized=35, reserved=35)
    assert accepted.status == "READY" and accepted.credits == 35


def test_pricing_stays_frozen_and_wrong_owner_or_session_is_rejected():
    q = quote([event(output_total=1500, input_uncached=0)],
              snapshot={"version": "v3", "output_per_million": 1200})
    assert q.price_version == "v3" and q.credits == 2
    with pytest.raises(ValueError, match="Cross-owner"):
        quote([event(owner_user_id="someone-else")])
    with pytest.raises(ValueError, match="Cross-session"):
        quote([event(billing_session_id="other")])


def test_pending_clarification_not_billable_until_task_final():
    result = quote([event("intent", "intent_v2")], final=False)
    assert result.status == "RECONCILING"
    result = quote([event("intent", "intent_v2")], delivered=False)
    assert result.status == "FREE"


def test_no_confirmed_usage_fails_closed():
    assert quote([], expected=0).status == "RECONCILING"
