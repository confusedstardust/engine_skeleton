from __future__ import annotations

import hashlib
import json
import re
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Mapping

from .config import CreditDatabaseConfig
from .errors import (
    CreditConflictError,
    CreditNotFoundError,
    CreditStateError,
    InsufficientCreditsError,
)
from .models import CreditBalance, CreditGrant, CreditReservation


ConnectionFactory = Callable[[], Any]
_ID_RE = re.compile(r"^[0-9a-fA-F]{32}$")
_OPERATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")
_SIGNUP_SOURCE_KEY = "signup-credits:v1"


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, (str, bytes, bytearray)):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    raise CreditStateError("Expected a JSON object from the database")


def _positive_units(units: int) -> int:
    if isinstance(units, bool) or not isinstance(units, int) or units <= 0:
        raise ValueError("units must be a positive integer")
    return units


def _validate_user_id(user_id: str) -> str:
    value = user_id.strip()
    if not value or len(value) > 191:
        raise ValueError("user_id must contain 1 to 191 characters")
    return value


def _validate_job_id(job_id: str) -> str:
    if not _ID_RE.fullmatch(job_id):
        raise ValueError("job_id must be a 32-character hexadecimal id")
    return job_id.lower()


def _validate_operation_key(operation_key: str) -> str:
    if not _OPERATION_RE.fullmatch(operation_key):
        raise ValueError("operation_key must be 1-64 safe ASCII characters")
    return operation_key


class MySQLCreditStore:
    """Transactional implementation for the credit tables in DDL_narrativeos_dev.sql."""

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connection_factory = connection_factory

    @classmethod
    def from_config(cls, config: CreditDatabaseConfig) -> "MySQLCreditStore":
        def connect():
            try:
                import pymysql
                from pymysql.cursors import DictCursor
            except ImportError as exc:  # pragma: no cover - installation problem
                raise RuntimeError("PyMySQL is required; install project requirements") from exc
            return pymysql.connect(cursorclass=DictCursor, **config.connect_kwargs())

        return cls(connect)

    @contextmanager
    def _transaction(self) -> Iterator[Any]:
        connection = self._connection_factory()
        try:
            connection.begin()
            with connection.cursor() as cursor:
                yield cursor
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def ensure_signup_grant(self, user_id: str, *, units: int = 200) -> CreditGrant:
        """Idempotently issue a promotional grant, without fabricating a payment."""
        user_id = _validate_user_id(user_id)
        units = _positive_units(units)
        if units != 200:
            raise ValueError("The v1 signup promotion is fixed at 200 credits")
        grant_id = _stable_id("signup-grant-v1", user_id)

        with self._transaction() as cursor:
            cursor.execute("SELECT id FROM users WHERE id=%s FOR UPDATE", (user_id,))
            if cursor.fetchone() is None:
                raise CreditNotFoundError(f"User does not exist: {user_id}")
            cursor.execute(
                "SELECT * FROM entitlement_grants WHERE user_id=%s AND source='PROMOTION' AND source_key=%s FOR UPDATE",
                (user_id, _SIGNUP_SOURCE_KEY),
            )
            existing = cursor.fetchone()
            if existing is not None:
                if existing["id"] != grant_id or int(existing["units_granted"]) != units:
                    raise CreditConflictError("Signup promotion exists with different credit data")
                return CreditGrant(grant_id, None, user_id, units, False)
            cursor.execute(
                """
                INSERT INTO entitlement_grants
                    (id, user_id, source, source_key, order_id, benefit_key, kind, status,
                     units_granted, units_available, units_reserved, units_consumed,
                     units_revoked, starts_at, expires_at, metadata_json)
                VALUES
                    (%s, %s, 'PROMOTION', %s, NULL, 'credits', 'CREDITS', 'ACTIVE',
                     %s, %s, 0, 0, 0, CURRENT_TIMESTAMP(3), NULL, %s)
                """,
                (
                    grant_id,
                    user_id,
                    _SIGNUP_SOURCE_KEY,
                    units,
                    units,
                    _canonical_json({"campaign": "signup", "schema_version": 1}),
                ),
            )
            self._insert_ledger(
                cursor,
                event_key=f"grant:{grant_id}",
                grant_id=grant_id,
                reservation_id=None,
                user_id=user_id,
                action="GRANT",
                deltas=(units, 0, 0, 0),
                after=(units, 0, 0, 0),
            )
            return CreditGrant(grant_id, None, user_id, units, True)

    def ensure_billable_job(
        self,
        *,
        user_id: str,
        job_id: str,
        source_material: str,
        options: Mapping[str, Any],
    ) -> None:
        """Idempotently mirror a Forge job into the billing schema."""
        user_id = _validate_user_id(user_id)
        job_id = _validate_job_id(job_id)
        options_json = _canonical_json(options)
        request_key = f"forge-job:{job_id}"
        request_hash = hashlib.sha256(
            _canonical_json({"source_material": source_material, "options": options}).encode("utf-8")
        ).hexdigest()
        title = str(options.get("classroom_topic") or "未命名课堂").strip()[:200] or "未命名课堂"

        with self._transaction() as cursor:
            cursor.execute("SELECT id FROM users WHERE id=%s FOR UPDATE", (user_id,))
            if cursor.fetchone() is None:
                raise CreditNotFoundError(f"User does not exist: {user_id}")
            cursor.execute("SELECT owner_user_id FROM games WHERE id=%s FOR UPDATE", (job_id,))
            game = cursor.fetchone()
            if game is None:
                cursor.execute(
                    """
                    INSERT INTO games (id, owner_user_id, title, status, visibility)
                    VALUES (%s, %s, %s, 'DRAFT', 'PRIVATE')
                    """,
                    (job_id, user_id, title),
                )
            elif game["owner_user_id"] != user_id:
                raise CreditConflictError("Game owner does not match the authenticated user")

            cursor.execute("SELECT owner_user_id, request_hash FROM generation_jobs WHERE id=%s FOR UPDATE", (job_id,))
            existing = cursor.fetchone()
            if existing is not None:
                if existing["owner_user_id"] != user_id or existing["request_hash"] != request_hash:
                    raise CreditConflictError("Generation job exists with different billing identity")
                return
            cursor.execute(
                """
                INSERT INTO generation_jobs
                    (id, game_id, owner_user_id, source_material, request_key, request_hash,
                     status, options_json, job_storage_prefix)
                VALUES (%s, %s, %s, %s, %s, %s, 'CREATED', %s, %s)
                """,
                (
                    job_id,
                    job_id,
                    user_id,
                    source_material,
                    request_key,
                    request_hash,
                    options_json,
                    f"jobs/{job_id}",
                ),
            )

    def fulfill_credit_order(self, order_id: str) -> CreditGrant:
        """Idempotently turn one PAID credit-pack order into an entitlement grant."""
        if not _ID_RE.fullmatch(order_id):
            raise ValueError("order_id must be a 32-character hexadecimal id")
        with self._transaction() as cursor:
            return self._grant_order_locked(cursor, order_id=order_id.lower())

    def _grant_order_locked(
        self,
        cursor: Any,
        *,
        order_id: str,
        expected_user_id: str | None = None,
        expected_grant_id: str | None = None,
    ) -> CreditGrant:
        cursor.execute("SELECT * FROM purchase_orders WHERE id=%s FOR UPDATE", (order_id,))
        order = cursor.fetchone()
        if order is None:
            raise CreditNotFoundError(f"Order does not exist: {order_id}")
        if expected_user_id is not None and order["user_id"] != expected_user_id:
            raise CreditConflictError("Order owner does not match the requested user")
        if order["status"] != "PAID":
            raise CreditStateError(f"Order must be PAID, got {order['status']}")
        if order["fulfillment_status"] == "REVOKED":
            raise CreditStateError("A revoked order cannot issue credits")
        snapshot = _json_object(order["product_snapshot"])
        if snapshot.get("kind") != "CREDIT_PACK":
            raise CreditStateError("Only CREDIT_PACK orders can issue credits")
        benefit = _json_object(snapshot.get("benefit"))
        units_per_item = _positive_units(benefit.get("credits"))
        units = units_per_item * int(order["quantity"])
        grant_id = expected_grant_id or _stable_id("order-credit-grant-v1", order_id)

        cursor.execute(
            "SELECT * FROM entitlement_grants WHERE order_id=%s AND benefit_key='credits' FOR UPDATE",
            (order_id,),
        )
        existing = cursor.fetchone()
        if existing is not None:
            if existing["id"] != grant_id or int(existing["units_granted"]) != units:
                raise CreditConflictError("Order was already fulfilled with different credit data")
            if order["fulfillment_status"] != "FULFILLED":
                cursor.execute(
                    "UPDATE purchase_orders SET fulfillment_status='FULFILLED', lock_version=lock_version+1 WHERE id=%s",
                    (order_id,),
                )
            return CreditGrant(grant_id, order_id, order["user_id"], units, False)
        if order["fulfillment_status"] == "FULFILLED":
            raise CreditStateError("Order is marked fulfilled but its credit grant is missing")

        cursor.execute(
            "UPDATE purchase_orders SET fulfillment_status='PROCESSING', lock_version=lock_version+1 WHERE id=%s",
            (order_id,),
        )
        cursor.execute(
            """
            INSERT INTO entitlement_grants
                (id, user_id, source, source_key, order_id, benefit_key, kind, status, units_granted,
                 units_available, units_reserved, units_consumed, units_revoked,
                 starts_at, expires_at, metadata_json)
            VALUES (%s, %s, 'ORDER', %s, %s, 'credits', 'CREDITS', 'ACTIVE', %s, %s, 0, 0, 0,
                    CURRENT_TIMESTAMP(3), NULL, %s)
            """,
            (
                grant_id,
                order["user_id"],
                order_id,
                order_id,
                units,
                units,
                _canonical_json({"source_order_id": order_id, "schema_version": 1}),
            ),
        )
        self._insert_ledger(
            cursor,
            event_key=f"grant:{grant_id}",
            grant_id=grant_id,
            reservation_id=None,
            user_id=order["user_id"],
            action="GRANT",
            deltas=(units, 0, 0, 0),
            after=(units, 0, 0, 0),
        )
        cursor.execute(
            "UPDATE purchase_orders SET fulfillment_status='FULFILLED', lock_version=lock_version+1 WHERE id=%s",
            (order_id,),
        )
        return CreditGrant(grant_id, order_id, order["user_id"], units, True)

    def get_balance(self, user_id: str) -> CreditBalance:
        user_id = _validate_user_id(user_id)
        with self._transaction() as cursor:
            self._expire_grants_locked(cursor, user_id)
            cursor.execute(
                """
                SELECT
                    COALESCE(SUM(CASE
                        WHEN status='ACTIVE'
                         AND starts_at <= CURRENT_TIMESTAMP(3)
                         AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP(3))
                        THEN units_available ELSE 0 END), 0) AS available,
                    COALESCE(SUM(units_reserved), 0) AS reserved,
                    COALESCE(SUM(units_consumed), 0) AS consumed,
                    COALESCE(SUM(units_revoked), 0) AS revoked
                FROM entitlement_grants
                WHERE user_id=%s AND kind='CREDITS'
                """,
                (user_id,),
            )
            row = cursor.fetchone()
            return CreditBalance(*(int(row[key]) for key in ("available", "reserved", "consumed", "revoked")))

    def reserve(
        self,
        *,
        user_id: str,
        job_id: str,
        operation_key: str,
        units: int,
        pricing_snapshot: Mapping[str, Any],
    ) -> CreditReservation:
        user_id = _validate_user_id(user_id)
        job_id = _validate_job_id(job_id)
        operation_key = _validate_operation_key(operation_key)
        units = _positive_units(units)
        pricing_json = _canonical_json(pricing_snapshot)
        reservation_id = _stable_id("credit-reservation-v1", job_id, operation_key)

        with self._transaction() as cursor:
            cursor.execute(
                "SELECT id FROM generation_jobs WHERE id=%s AND owner_user_id=%s FOR UPDATE",
                (job_id, user_id),
            )
            if cursor.fetchone() is None:
                raise CreditNotFoundError("Generation job does not exist or is owned by another user")
            cursor.execute(
                "SELECT * FROM credit_reservations WHERE job_id=%s AND operation_key=%s FOR UPDATE",
                (job_id, operation_key),
            )
            existing = cursor.fetchone()
            if existing is not None:
                if (
                    existing["user_id"] != user_id
                    or int(existing["units"]) != units
                    or _canonical_json(_json_object(existing["pricing_snapshot"])) != pricing_json
                ):
                    raise CreditConflictError("Credit operation key was reused with different data")
                return CreditReservation(
                    existing["id"], user_id, job_id, operation_key, units, existing["status"], False
                )
            cursor.execute(
                "SELECT id FROM credit_reservations WHERE job_id=%s AND status='RESERVED' FOR UPDATE",
                (job_id,),
            )
            if cursor.fetchone() is not None:
                raise CreditConflictError("This job already has an active credit reservation")

            self._expire_grants_locked(cursor, user_id)
            cursor.execute(
                """
                SELECT * FROM entitlement_grants
                WHERE user_id=%s AND kind='CREDITS' AND status='ACTIVE'
                  AND starts_at <= CURRENT_TIMESTAMP(3)
                  AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP(3))
                  AND units_available > 0
                ORDER BY (expires_at IS NULL), expires_at, created_at, id
                FOR UPDATE
                """,
                (user_id,),
            )
            grants = cursor.fetchall()
            available = sum(int(grant["units_available"]) for grant in grants)
            if available < units:
                raise InsufficientCreditsError(required=units, available=available)

            cursor.execute(
                """
                INSERT INTO credit_reservations
                    (id, user_id, job_id, operation_key, units, status, pricing_snapshot)
                VALUES (%s, %s, %s, %s, %s, 'RESERVED', %s)
                """,
                (reservation_id, user_id, job_id, operation_key, units, pricing_json),
            )
            remaining = units
            for grant in grants:
                if remaining == 0:
                    break
                allocated = min(remaining, int(grant["units_available"]))
                after = (
                    int(grant["units_available"]) - allocated,
                    int(grant["units_reserved"]) + allocated,
                    int(grant["units_consumed"]),
                    int(grant["units_revoked"]),
                )
                cursor.execute(
                    """
                    UPDATE entitlement_grants
                    SET units_available=%s, units_reserved=%s
                    WHERE id=%s AND user_id=%s
                    """,
                    (after[0], after[1], grant["id"], user_id),
                )
                cursor.execute(
                    "INSERT INTO credit_allocations (reservation_id, grant_id, user_id, units) VALUES (%s,%s,%s,%s)",
                    (reservation_id, grant["id"], user_id, allocated),
                )
                self._insert_ledger(
                    cursor,
                    event_key=f"reserve:{reservation_id}",
                    grant_id=grant["id"],
                    reservation_id=reservation_id,
                    user_id=user_id,
                    action="RESERVE",
                    deltas=(-allocated, allocated, 0, 0),
                    after=after,
                )
                remaining -= allocated
            return CreditReservation(reservation_id, user_id, job_id, operation_key, units, "RESERVED", True)

    def capture(
        self,
        reservation_id: str,
        *,
        units: int | None = None,
        settlement: Mapping[str, Any] | None = None,
    ) -> CreditReservation:
        return self._settle(reservation_id, target="CAPTURED", capture_units=units, settlement=settlement)

    def release(self, reservation_id: str) -> CreditReservation:
        return self._settle(reservation_id, target="RELEASED")

    def _settle(
        self,
        reservation_id: str,
        *,
        target: str,
        capture_units: int | None = None,
        settlement: Mapping[str, Any] | None = None,
    ) -> CreditReservation:
        if not _ID_RE.fullmatch(reservation_id):
            raise ValueError("reservation_id must be a 32-character hexadecimal id")
        action = "CAPTURE" if target == "CAPTURED" else "RELEASE"
        with self._transaction() as cursor:
            cursor.execute("SELECT * FROM credit_reservations WHERE id=%s FOR UPDATE", (reservation_id,))
            reservation = cursor.fetchone()
            if reservation is None:
                raise CreditNotFoundError(f"Reservation does not exist: {reservation_id}")
            if reservation["status"] == target:
                return self._reservation_model(reservation, created=False)
            if reservation["status"] != "RESERVED":
                raise CreditStateError(
                    f"Cannot {action.lower()} a {reservation['status']} reservation"
                )
            reserved_units = int(reservation["units"])
            if capture_units is None:
                capture_units = reserved_units if target == "CAPTURED" else 0
            if isinstance(capture_units, bool) or not isinstance(capture_units, int) or not 0 <= capture_units <= reserved_units:
                raise CreditStateError("Captured units must be between zero and the reserved units")
            cursor.execute(
                """
                SELECT a.units AS allocated_units, g.*
                FROM credit_allocations a
                JOIN entitlement_grants g ON g.id=a.grant_id AND g.user_id=a.user_id
                WHERE a.reservation_id=%s
                ORDER BY g.id FOR UPDATE
                """,
                (reservation_id,),
            )
            allocations = cursor.fetchall()
            if sum(int(row["allocated_units"]) for row in allocations) != int(reservation["units"]):
                raise CreditStateError("Reservation allocations do not match its units")

            remaining_capture = capture_units
            for grant in allocations:
                allocated = int(grant["allocated_units"])
                if int(grant["units_reserved"]) < allocated:
                    raise CreditStateError("Grant reserved balance is inconsistent")
                captured = min(allocated, remaining_capture) if target == "CAPTURED" else 0
                released = allocated - captured
                remaining_capture -= captured
                after = (
                    int(grant["units_available"]) + released,
                    int(grant["units_reserved"]) - allocated,
                    int(grant["units_consumed"]) + captured,
                    int(grant["units_revoked"]),
                )
                deltas = (released, -allocated, captured, 0)
                cursor.execute(
                    """
                    UPDATE entitlement_grants
                    SET units_available=%s, units_reserved=%s, units_consumed=%s, units_revoked=%s
                    WHERE id=%s AND user_id=%s
                    """,
                    (*after, grant["id"], reservation["user_id"]),
                )
                self._insert_ledger(
                    cursor,
                    event_key=f"{action.lower()}:{reservation_id}",
                    grant_id=grant["id"],
                    reservation_id=reservation_id,
                    user_id=reservation["user_id"],
                    action=action,
                    deltas=deltas,
                    after=after,
                )
            pricing_snapshot = _json_object(reservation["pricing_snapshot"])
            pricing_snapshot["settled_units"] = capture_units
            if settlement is not None:
                pricing_snapshot["settlement"] = dict(settlement)
            cursor.execute(
                "UPDATE credit_reservations SET status=%s, pricing_snapshot=%s, settled_at=CURRENT_TIMESTAMP(3) WHERE id=%s",
                (target, _canonical_json(pricing_snapshot), reservation_id),
            )
            self._expire_grants_locked(cursor, reservation["user_id"])
            reservation["status"] = target
            return self._reservation_model(reservation, created=False)

    def _expire_grants_locked(self, cursor: Any, user_id: str) -> None:
        cursor.execute(
            """
            SELECT * FROM entitlement_grants
            WHERE user_id=%s AND kind='CREDITS' AND status='ACTIVE'
              AND expires_at IS NOT NULL AND expires_at <= CURRENT_TIMESTAMP(3)
              AND units_reserved=0
            ORDER BY id FOR UPDATE
            """,
            (user_id,),
        )
        for grant in cursor.fetchall():
            expired = int(grant["units_available"])
            after = (
                0,
                int(grant["units_reserved"]),
                int(grant["units_consumed"]),
                int(grant["units_revoked"]) + expired,
            )
            cursor.execute(
                """
                UPDATE entitlement_grants
                SET status='EXPIRED', units_available=0, units_revoked=%s
                WHERE id=%s AND user_id=%s
                """,
                (after[3], grant["id"], user_id),
            )
            self._insert_ledger(
                cursor,
                event_key=f"expire:{grant['id']}",
                grant_id=grant["id"],
                reservation_id=None,
                user_id=user_id,
                action="EXPIRE",
                deltas=(-expired, 0, 0, expired),
                after=after,
            )

    @staticmethod
    def _insert_ledger(
        cursor: Any,
        *,
        event_key: str,
        grant_id: str,
        reservation_id: str | None,
        user_id: str,
        action: str,
        deltas: tuple[int, int, int, int],
        after: tuple[int, int, int, int],
    ) -> None:
        cursor.execute(
            """
            INSERT INTO credit_ledger
                (event_key, grant_id, reservation_id, user_id, action,
                 delta_available, delta_reserved, delta_consumed, delta_revoked,
                 available_after, reserved_after, consumed_after, revoked_after)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (event_key, grant_id, reservation_id, user_id, action, *deltas, *after),
        )

    @staticmethod
    def _reservation_model(row: Mapping[str, Any], *, created: bool) -> CreditReservation:
        return CreditReservation(
            row["id"],
            row["user_id"],
            row["job_id"],
            row["operation_key"],
            int(row["units"]),
            row["status"],
            created,
        )
