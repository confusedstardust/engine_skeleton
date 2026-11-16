"""Isolated MySQL-8 schema and event-idempotency test for additive Billing V2.

CI must provision NAR_TEST_DB_NAME=nar_conversation_test; never use production.
"""
import os
import uuid
from pathlib import Path

import pytest
import pymysql
from pymysql.cursors import DictCursor

from webgal_backend.nar_metering_v2 import NormalizedUsage
from webgal_backend.nar_usage_store_v2 import NarUsageEventStore, ModelUsageEvent


@pytest.fixture(scope="module")
def metering_db():
    if os.environ.get("NAR_TEST_DB_NAME") != "nar_conversation_test":
        pytest.skip("Dedicated disposable MySQL database only")
    params = dict(host="127.0.0.1", port=3306, user="root",
                  password=os.environ["NAR_TEST_DB_PASSWORD"], database="nar_conversation_test",
                  charset="utf8mb4", autocommit=False, cursorclass=DictCursor)
    def factory():
        return pymysql.connect(**params)
    migration = Path("credit_system/migrations/006_nar_billing_v2.sql").read_text()
    statements = "\n".join(line for line in migration.splitlines()
                          if not line.lstrip().startswith("--")).split(";")
    with factory() as connection:
        with connection.cursor() as cursor:
            for statement in statements:
                if statement.strip():
                    cursor.execute(statement)
        connection.commit()
    return NarUsageEventStore(factory), factory


def test_v2_schema_immutable_event_replay_and_owner_partition(metering_db):
    store, factory = metering_db
    identifier = uuid.uuid4().hex
    turn = uuid.uuid4().hex
    event = ModelUsageEvent(
        event_key="test.v2." + identifier,
        owner_user_id="test-owner-" + identifier, turn_id=turn,
        conversation_id=uuid.uuid4().hex, call_id=identifier,
        stage="intent_v2", provider="deepseek",
        usage=NormalizedUsage(100, 100, 0, 10),
        billable_to_user=True,
    )
    assert store.record(event) is True
    assert store.record(event) is False
    with factory() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT owner_user_id, turn_id, input_uncached, cache_read_input "
                           "FROM nar_usage_events WHERE event_key=%s", (event.event_key,))
            row = cursor.fetchone()
            assert row["owner_user_id"] == event.owner_user_id
            assert row["turn_id"] == turn
            assert (row["input_uncached"], row["cache_read_input"]) == (100, 100)
            cursor.execute("SELECT COUNT(*) AS total FROM nar_usage_events WHERE event_key=%s",
                           (event.event_key,))
            assert cursor.fetchone()["total"] == 1
    different = ModelUsageEvent(
        event_key=event.event_key, owner_user_id="other-owner", turn_id=turn,
        call_id=identifier, stage="intent_v2", provider="deepseek",
        usage=NormalizedUsage(100, 100, 0, 10),
    )
    with pytest.raises(ValueError, match="Conflicting"):
        store.record(different)


def test_v2_schema_has_unique_extension_sequence(metering_db):
    _, factory = metering_db
    reservation = uuid.uuid4().hex
    with factory() as connection:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO nar_reservation_extensions "
                           "(id,reservation_id,sequence_no,delta_credits) VALUES (%s,%s,1,20)",
                           (uuid.uuid4().hex, reservation))
            with pytest.raises(pymysql.IntegrityError):
                cursor.execute("INSERT INTO nar_reservation_extensions "
                               "(id,reservation_id,sequence_no,delta_credits) VALUES (%s,%s,1,20)",
                               (uuid.uuid4().hex, reservation))
        connection.rollback()


def test_real_wallet_extension_and_capture_in_disposable_mysql(monkeypatch):
    """Credit reservation, top-up and capture execute against actual InnoDB SQL.

    All wallet tables are session-local TEMPORARY; production tables are never read.
    """
    if os.environ.get("NAR_TEST_DB_NAME") != "nar_conversation_test":
        pytest.skip("Dedicated disposable MySQL only")
    from credit_system.store import MySQLCreditStore
    import credit_system.subscriptions as subscriptions

    params = dict(host="127.0.0.1", port=3306, user="root",
                  password=os.environ["NAR_TEST_DB_PASSWORD"],
                  database="nar_conversation_test", charset="utf8mb4",
                  autocommit=False, cursorclass=DictCursor)
    connection = pymysql.connect(**params)
    owner, job = "wallet-ci-" + uuid.uuid4().hex, uuid.uuid4().hex
    try:
        with connection.cursor() as cur:
            cur.execute("CREATE TEMPORARY TABLE users (id varchar(191) PRIMARY KEY)")
            cur.execute("CREATE TEMPORARY TABLE generation_jobs "
                        "(id char(32) PRIMARY KEY, owner_user_id varchar(191))")
            cur.execute("""CREATE TEMPORARY TABLE credit_reservations (
                id char(32) PRIMARY KEY,user_id varchar(191) NOT NULL,
                job_id char(32),operation_key varchar(64),units int NOT NULL,
                status varchar(32) NOT NULL,pricing_snapshot JSON NOT NULL,
                settled_at datetime(3) NULL,
                UNIQUE KEY uq_operation (job_id,operation_key)
            )""")
            cur.execute("""CREATE TEMPORARY TABLE entitlement_grants (
                id char(32) PRIMARY KEY,user_id varchar(191) NOT NULL,
                source varchar(32),source_key varchar(64),benefit_key varchar(64),
                kind varchar(32) NOT NULL,status varchar(32) NOT NULL,
                units_granted bigint NOT NULL,units_available bigint NOT NULL,
                units_reserved bigint NOT NULL,units_consumed bigint NOT NULL,
                units_revoked bigint NOT NULL,
                starts_at datetime(3) NOT NULL,expires_at datetime(3),
                created_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
                metadata_json JSON NULL
            )""")
            cur.execute("""CREATE TEMPORARY TABLE credit_allocations (
                reservation_id char(32),grant_id char(32),user_id varchar(191),
                units bigint NOT NULL,PRIMARY KEY (reservation_id,grant_id)
            )""")
            cur.execute("""CREATE TEMPORARY TABLE credit_ledger (
                event_key varchar(191),grant_id char(32),reservation_id char(32),
                user_id varchar(191),action varchar(32),
                delta_available bigint,delta_reserved bigint,
                delta_consumed bigint,delta_revoked bigint,
                available_after bigint,reserved_after bigint,
                consumed_after bigint,revoked_after bigint,
                PRIMARY KEY(event_key,grant_id)
            )""")
            cur.execute("INSERT INTO users (id) VALUES (%s)", (owner,))
            cur.execute("INSERT INTO generation_jobs (id,owner_user_id) VALUES (%s,%s)",
                        (job, owner))
            cur.execute("""INSERT INTO entitlement_grants (
                id,user_id,source,source_key,benefit_key,kind,status,
                units_granted,units_available,units_reserved,units_consumed,units_revoked,
                starts_at) VALUES (%s,%s,'PROMOTION','ci','credits','CREDITS',
                'ACTIVE',70,70,0,0,0,CURRENT_TIMESTAMP(3))""",
                (uuid.uuid4().hex, owner))
        connection.commit()

        class SessionConnection:
            def begin(self): connection.begin()
            def cursor(self): return connection.cursor()
            def commit(self): connection.commit()
            def rollback(self): connection.rollback()
            def close(self): pass

        monkeypatch.setattr(subscriptions, "issue_for_user", lambda *a, **k: 0)
        store = MySQLCreditStore(lambda: SessionConnection())
        original = store.reserve(user_id=owner,job_id=job,
                                 operation_key="nar-agent-turn-v1",units=20,
                                 pricing_snapshot={"schema_version":2,"pricing":{"test":1}})
        assert original.units == 20
        first = store.extend_reservation(user_id=owner,
                                         reservation_id=original.reservation_id,
                                         delta_units=15, sequence_no=1,
                                         authorized_total=35)
        assert first.units == 35
        repeat = store.extend_reservation(user_id=owner,
                                          reservation_id=original.reservation_id,
                                          delta_units=15, sequence_no=1,
                                          authorized_total=35)
        assert repeat.units == 35
        with pytest.raises(Exception):
            store.extend_reservation(user_id=owner,
                                     reservation_id=original.reservation_id,
                                     delta_units=14, sequence_no=1,
                                     authorized_total=40)
        with pytest.raises(Exception):
            store.extend_reservation(user_id="another-user",
                                     reservation_id=original.reservation_id,
                                     delta_units=1, sequence_no=2,
                                     authorized_total=40)
        store.capture(original.reservation_id, units=35)
        with connection.cursor() as cur:
            cur.execute("SELECT units, status FROM credit_reservations WHERE id=%s",
                        (original.reservation_id,))
            reservation = cur.fetchone()
            assert reservation["units"] == 35 and reservation["status"] == "CAPTURED"
            cur.execute("""SELECT SUM(units_available) AS available,
                SUM(units_reserved) AS reserved,SUM(units_consumed) AS consumed
                FROM entitlement_grants WHERE user_id=%s""",(owner,))
            balance=cur.fetchone()
            assert (balance["available"], balance["reserved"],
                    balance["consumed"]) == (35,0,35)
            cur.execute("SELECT COUNT(*) AS n FROM nar_reservation_extensions "
                        "WHERE reservation_id=%s",(original.reservation_id,))
            assert cur.fetchone()["n"] == 1
    finally:
        connection.close()
