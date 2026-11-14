"""Ephemeral MySQL 8 CI test. NEVER point this test at a user/production DB.

The CI job creates a disposable service with MYSQL_DATABASE=nar_conversation_test.
The product does NOT execute migration SQL on startup or during normal requests.
"""
import os
import uuid
from pathlib import Path

import pymysql
import pytest
from pymysql.cursors import DictCursor

from forge_database import Database
from webgal_backend.nar_conversation_store import (
    ConversationConflict, ConversationMissing, NarConversationStore,
)


@pytest.fixture(scope="module")
def ledger():
    if os.getenv("NAR_TEST_DB_NAME") != "nar_conversation_test":
        pytest.skip("Runs only against the dedicated ephemeral CI test DB")
    params = dict(host="127.0.0.1", port=3306, user="root",
                  password=os.environ["NAR_TEST_DB_PASSWORD"], database="nar_conversation_test",
                  charset="utf8mb4", autocommit=False, cursorclass=DictCursor)
    def connection():
        return pymysql.connect(**params)
    migration = Path("webgal_backend/migrations/002_nar_conversation_history.sql").read_text()
    statements = "\n".join(line for line in migration.splitlines()
                           if not line.strip().startswith("--")).split(";")
    with connection() as conn:
        with conn.cursor() as cursor:
            for statement in statements:
                if statement.strip():
                    cursor.execute(statement)
        conn.commit()
    return NarConversationStore(transaction=Database(connection).transaction)


def test_schema_and_transactional_idempotency(ledger):
    assert ledger.ready()
    owner, cid = "ci-" + uuid.uuid4().hex, uuid.uuid4().hex
    aid, request = uuid.uuid4().hex, uuid.uuid4().hex
    turn, new = ledger.start_turn(owner, cid, request, "学会串并联电路", "html", create=True)
    assert new and turn["status"] == "QUEUED"
    repeat, new_again = ledger.start_turn(owner, cid, request, "学会串并联电路", "html", create=True)
    assert not new_again and repeat["id"] == turn["id"]
    with pytest.raises(ConversationConflict):
        ledger.start_turn(owner, cid, request, "同一幂等键不许改成别的请求", "html", create=True)
    assert ledger.model_history(owner, cid, turn["id"]) == []
    with pytest.raises(ConversationConflict):
        ledger.start_turn(owner, cid, uuid.uuid4().hex, "另一个同时发送", "chat")
    ledger.mark_running(owner, cid, turn["id"], uuid.uuid4().hex)
    done = ledger.finish_turn(owner, cid, turn["id"], output="已生成电路实验",
                              artifact_id=aid, title="初中电路实验", kind="html",
                              public_metadata={"publicBrief": "串联与并联"})
    assert done["status"] == "SUCCEEDED"
    ledger.finish_turn(owner, cid, turn["id"], output="必须幂等")
    detail = ledger.get_detail(owner, cid)
    assert len(detail["messages"]) == 2
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["content"] == "已生成电路实验"
    assert detail["artifacts"][0]["artifactId"] == aid
    assert detail["artifacts"][0]["originMessageId"] == detail["messages"][1]["id"]
    assert ledger.list_conversations(owner)["items"][0]["id"] == cid
    assert ledger.artifact_history(owner)["items"][0]["artifactId"] == aid
    assert len(ledger.get_messages(owner, cid, before=2)["items"]) == 1
    ledger.link_work(owner, cid, aid, uuid.uuid4().hex)
    assert ledger.get_detail(owner, cid)["artifacts"][0]["workId"] is not None
    second, created = ledger.start_turn(owner, cid, uuid.uuid4().hex, "继续讲解", "chat")
    assert created
    assert [m["content"] for m in ledger.model_history(owner, cid, second["id"])] == [
        "学会串并联电路", "已生成电路实验"
    ]
    with pytest.raises(ConversationMissing):
        ledger.get_detail("ci-different-account", cid)
    with pytest.raises(ConversationMissing):
        ledger.get_turn("ci-different-account", cid, turn["id"])
    assert ledger.list_conversations("ci-different-account")["items"] == []
    assert ledger.artifact_history("ci-different-account")["items"] == []
    ledger.fail_turn(owner, cid, second["id"], "TEST", uncertain=True)
    with pytest.raises(ConversationConflict):
        ledger.start_turn(owner, cid, uuid.uuid4().hex, "未知状态不允许自动新轮次", "chat")


def test_keyset_pagination_and_owner_scope(ledger):
    owner = "ci-" + uuid.uuid4().hex
    ids = [uuid.uuid4().hex for _ in range(3)]
    for cid in ids:
        turn, _ = ledger.start_turn(owner, cid, uuid.uuid4().hex, "测试分页", "chat", create=True)
        ledger.fail_turn(owner, cid, turn["id"], "TEST")
    first = ledger.list_conversations(owner, limit=1)
    assert len(first["items"]) == 1 and first["nextCursor"]
    second = ledger.list_conversations(owner, limit=1, cursor=first["nextCursor"])
    assert len(second["items"]) == 1
    assert second["items"][0]["id"] != first["items"][0]["id"]
    with pytest.raises(ValueError):
        ledger.list_conversations(owner, limit=1, cursor="malformed_cursor!")
