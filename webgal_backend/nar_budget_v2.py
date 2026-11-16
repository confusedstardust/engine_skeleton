"""Pure Budget V2 admission math, before any provider call is dispatched.

No endpoint is enabled until the durable turn/budget gateway is implemented.
These functions never mutate wallets and never estimate actual billable usage.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_CEILING


class BudgetApprovalRequired(Exception):
    """Call must pause; it must not be sent to the provider."""


def _valid_amount(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError("Usage estimate must be a finite nonnegative Decimal")
    return value


def extension_needed(*, incurred: Decimal, next_call_upper_bound: Decimal,
                     reserved_credits: int, authorized_credits: int,
                     usage_complete: bool = True) -> int:
    """Credits to reserve before the next model/tool request.

    The input bound is a conservative budget estimate. The final user invoice
    must come only from authoritative provider-reported usage.
    """
    _valid_amount(incurred)
    _valid_amount(next_call_upper_bound)
    if (isinstance(reserved_credits, bool) or isinstance(authorized_credits, bool)
            or not isinstance(reserved_credits, int) or not isinstance(authorized_credits, int)
            or reserved_credits < 0 or authorized_credits < 0
            or reserved_credits > authorized_credits):
        raise ValueError("Invalid reservation or authorized budget")
    if not usage_complete:
        raise BudgetApprovalRequired("Uncertain usage must be reconciled before further calls")
    needed = int((incurred + next_call_upper_bound).to_integral_value(rounding=ROUND_CEILING))
    if needed > authorized_credits:
        raise BudgetApprovalRequired("Next call would exceed the user's authorized budget")
    return max(0, needed - reserved_credits)
