from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CreditBalance:
    available: int
    reserved: int
    consumed: int
    revoked: int


@dataclass(frozen=True)
class CreditGrant:
    grant_id: str
    order_id: str | None
    user_id: str
    units: int
    created: bool


@dataclass(frozen=True)
class CreditReservation:
    reservation_id: str
    user_id: str
    job_id: str
    operation_key: str
    units: int
    status: str
    created: bool
