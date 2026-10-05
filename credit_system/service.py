from __future__ import annotations

from typing import Any, Mapping

from .config import CreditDatabaseConfig
from .models import CreditBalance, CreditGrant, CreditReservation
from .store import MySQLCreditStore


class CreditService:
    """Stable business-facing API for registration, orders, and job charging."""

    def __init__(self, store: MySQLCreditStore) -> None:
        self._store = store

    @classmethod
    def from_env(cls) -> "CreditService":
        return cls(MySQLCreditStore.from_config(CreditDatabaseConfig.from_env()))

    def ensure_signup_credits(self, user_id: str) -> CreditGrant:
        """Give a database user the one-time 200-credit registration benefit."""
        return self._store.ensure_signup_grant(user_id, units=200)

    def get_balance(self, user_id: str) -> CreditBalance:
        return self._store.get_balance(user_id)

    def ensure_billable_job(
        self,
        *,
        user_id: str,
        job_id: str,
        source_material: str,
        options: Mapping[str, Any],
    ) -> None:
        self._store.ensure_billable_job(
            user_id=user_id,
            job_id=job_id,
            source_material=source_material,
            options=options,
        )

    def fulfill_paid_order(self, order_id: str) -> CreditGrant:
        """Issue credits for a locally verified PAID credit-pack order."""
        return self._store.fulfill_credit_order(order_id)

    def reserve_for_game(
        self,
        *,
        user_id: str,
        job_id: str,
        operation_key: str,
        units: int,
        pricing_snapshot: Mapping[str, Any] | None = None,
    ) -> CreditReservation:
        return self._store.reserve(
            user_id=user_id,
            job_id=job_id,
            operation_key=operation_key,
            units=units,
            pricing_snapshot=pricing_snapshot
            or {"schema_version": 2, "plan": "metered_generation_v1", "hold_units": units},
        )

    def capture(self, reservation_id: str, units: int | None = None, settlement: Mapping[str, Any] | None = None) -> CreditReservation:
        """Permanently charge a successful generation operation."""
        return self._store.capture(reservation_id, units=units, settlement=settlement)

    def release(self, reservation_id: str) -> CreditReservation:
        """Return frozen credits after a definite generation failure."""
        return self._store.release(reservation_id)
