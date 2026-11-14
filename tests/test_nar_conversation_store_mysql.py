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
    saved_work_id = uuid.uuid4().hex
    ledger.link_work(owner, cid, aid, saved_work_id)
    ledger.link_work(owner, cid, aid, saved_work_id)  # idempotent retry
    with pytest.raises(ConversationConflict):
        ledger.link_work(owner, cid, aid, uuid.uuid4().hex)
    assert ledger.get_detail(owner, cid)["artifacts"][0]["workId"] == saved_work_id
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

def test_artifact_history_groups_multiple_sources(ledger):
    owner = "ci-" + uuid.uuid4().hex
    artifact = uuid.uuid4().hex
    sessions = [uuid.uuid4().hex, uuid.uuid4().hex]
    for cid in sessions:
        t, _ = ledger.start_turn(owner, cid, uuid.uuid4().hex, "制作同一课堂的后续练习", "html", create=True)
        ledger.finish_turn(owner, cid, t["id"], output="作品关联完成", artifact_id=artifact,
                           title="共用产物", kind="html")
    history = ledger.artifact_history(owner, limit=1)
    assert len(history["items"]) == 1
    assert history["items"][0]["artifactId"] == artifact
    assert {source["conversationId"] for source in history["items"][0]["sources"]} == set(sessions)
    assert history["nextCursor"] is None
    assert ledger.artifact_history("ci-other-user", limit=30)["items"] == []

def test_failed_html_turn_persists_real_public_reason_and_phase(ledger):
    owner, cid = "ci-" + uuid.uuid4().hex, uuid.uuid4().hex
    turn, created = ledger.start_turn(owner, cid, uuid.uuid4().hex,
        "生成串并联电路实验", "html", create=True)
    assert created
    failed = ledger.fail_turn(owner, cid, turn["id"], "MODEL_AUTH_FAILED",
        public_error="模型服务认证或权限验证失败，请检查模型服务凭据与权限。",
        phase="DESIGNING")
    assert failed["status"] == "FAILED"
    messages = ledger.get_detail(owner, cid)["messages"]
    assert len(messages) == 2
    assert "模型服务认证" in messages[1]["content"]
    assert messages[1]["metadata"]["phase"] == "DESIGNING"
    assert messages[1]["metadata"]["errorCode"] == "MODEL_AUTH_FAILED"
    # Repeated status polls never duplicate a persisted failure message.
    ledger.fail_turn(owner, cid, turn["id"], "MODEL_AUTH_FAILED",
        public_error="duplicated failure message")
    assert len(ledger.get_detail(owner, cid)["messages"]) == 2
    # A failed turn releases the conversation for future new work.
    next_turn, new = ledger.start_turn(owner, cid, uuid.uuid4().hex, "换个任务", "chat")
    assert new and next_turn["status"] == "QUEUED"
