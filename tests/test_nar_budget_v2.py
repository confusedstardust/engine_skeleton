import pytest
from decimal import Decimal
from webgal_backend.nar_budget_v2 import BudgetApprovalRequired, extension_needed


def test_dynamic_hold_35_credits_with_initial_20():
    assert extension_needed(incurred=Decimal("19.4"),
        next_call_upper_bound=Decimal("15.6"),
        reserved_credits=20, authorized_credits=35) == 15


def test_no_provider_call_when_user_has_not_authorized_more():
    with pytest.raises(BudgetApprovalRequired):
        extension_needed(incurred=Decimal("19.4"), next_call_upper_bound=Decimal("15.6"),
                         reserved_credits=20, authorized_credits=20)


def test_reuses_adequate_hold_and_blocks_unknown_usage():
    assert extension_needed(incurred=Decimal("4.1"), next_call_upper_bound=Decimal("2"),
                            reserved_credits=20, authorized_credits=30) == 0
    with pytest.raises(BudgetApprovalRequired):
        extension_needed(incurred=Decimal("1"), next_call_upper_bound=Decimal("1"),
                         reserved_credits=20, authorized_credits=30,
                         usage_complete=False)


def test_nonfinite_or_malformed_prices_fail_closed():
    with pytest.raises(ValueError):
        extension_needed(incurred=Decimal("NaN"), next_call_upper_bound=Decimal("1"),
                         reserved_credits=20, authorized_credits=30)
    with pytest.raises(ValueError):
        extension_needed(incurred=Decimal("0"), next_call_upper_bound=Decimal("-1"),
                         reserved_credits=20, authorized_credits=30)
    with pytest.raises(ValueError):
        extension_needed(incurred=Decimal("0"), next_call_upper_bound=Decimal("1"),
                         reserved_credits=True, authorized_credits=30)
