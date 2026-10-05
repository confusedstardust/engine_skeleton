from __future__ import annotations

import pytest

from credit_system import CreditConfigurationError, CreditDatabaseConfig, CreditService
from credit_system.models import CreditBalance, CreditGrant, CreditReservation
from credit_system.store import _canonical_json, _stable_id


class FakeStore:
    def __init__(self) -> None:
        self.calls = []

    def ensure_signup_grant(self, user_id, *, units):
        self.calls.append(("signup", user_id, units))
        return CreditGrant("g" * 32, None, user_id, units, True)

    def get_balance(self, user_id):
        self.calls.append(("balance", user_id))
        return CreditBalance(200, 0, 0, 0)

    def ensure_billable_job(self, **kwargs):
        self.calls.append(("billable_job", kwargs))

    def fulfill_credit_order(self, order_id):
        self.calls.append(("fulfill", order_id))
        return CreditGrant("g" * 32, order_id, "user-1", 100, True)

    def reserve(self, **kwargs):
        self.calls.append(("reserve", kwargs))
        return CreditReservation(
            "r" * 32,
            kwargs["user_id"],
            kwargs["job_id"],
            kwargs["operation_key"],
            kwargs["units"],
            "RESERVED",
            True,
        )

    def capture(self, reservation_id, *, units=None, settlement=None):
        self.calls.append(("capture", reservation_id, units, settlement))
        return CreditReservation(reservation_id, "user-1", "a" * 32, "initial", 100, "CAPTURED", False)

    def release(self, reservation_id):
        self.calls.append(("release", reservation_id))
        return CreditReservation(reservation_id, "user-1", "a" * 32, "initial", 100, "RELEASED", False)


def test_business_facade_reserves_and_settles_a_metered_generation():
    store = FakeStore()
    service = CreditService(store)

    grant = service.ensure_signup_credits("user-1")
    service.ensure_billable_job(
        user_id="user-1",
        job_id="a" * 32,
        source_material="lesson",
        options={"classroom_topic": "示例课堂"},
    )
    reservation = service.reserve_for_game(
        user_id="user-1",
        job_id="a" * 32,
        operation_key="initial-generation-v1",
        units=60,
        pricing_snapshot={"schema_version": 2, "plan": "metered_generation_v1"},
    )
    service.capture(reservation.reservation_id, units=37, settlement={"text": 12, "images": 25})

    assert grant.units == 200
    assert store.calls[0] == ("signup", "user-1", 200)
    assert store.calls[1] == (
        "billable_job",
        {
            "user_id": "user-1",
            "job_id": "a" * 32,
            "source_material": "lesson",
            "options": {"classroom_topic": "示例课堂"},
        },
    )
    assert store.calls[2][1]["units"] == 60
    assert store.calls[2][1]["pricing_snapshot"] == {"schema_version": 2, "plan": "metered_generation_v1"}
    assert store.calls[3] == ("capture", "r" * 32, 37, {"text": 12, "images": 25})


def test_stable_ids_and_json_are_deterministic():
    assert _stable_id("a", "b") == _stable_id("a", "b")
    assert len(_stable_id("a", "b")) == 32
    assert _canonical_json({"z": 1, "a": "中文"}) == '{"a":"中文","z":1}'


def test_database_password_is_not_exposed_in_repr():
    config = CreditDatabaseConfig(
        host="127.0.0.1",
        port=3306,
        user="app",
        password="super-secret",
        database="narrativeos_dev",
    )
    assert "super-secret" not in repr(config)
    assert config.connect_kwargs()["autocommit"] is False


def test_database_url_is_supported_without_leaking_password(monkeypatch):
    monkeypatch.setenv(
        "NARRATIVEOS_DATABASE_URL",
        "mysql://app:p%40ss%21@db.example.com:3307/narrativeos_dev",
    )
    config = CreditDatabaseConfig.from_env()
    assert config.host == "db.example.com"
    assert config.port == 3307
    assert config.user == "app"
    assert config.password == "p@ss!"
    assert config.database == "narrativeos_dev"
    assert "p@ss!" not in repr(config)


def test_signup_configuration_is_required(monkeypatch):
    monkeypatch.delenv("NARRATIVEOS_DATABASE_URL", raising=False)
    for name in ("CREDIT_DB_HOST", "CREDIT_DB_USER", "CREDIT_DB_PASSWORD", "CREDIT_DB_NAME"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(CreditConfigurationError, match="CREDIT_DB_HOST"):
        CreditDatabaseConfig.from_env()
