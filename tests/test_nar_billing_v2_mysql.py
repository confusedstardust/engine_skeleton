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
