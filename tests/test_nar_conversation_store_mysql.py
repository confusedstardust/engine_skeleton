"""Ephemeral MySQL 8 CI test. NEVER point this test at a user/production DB.

The CI job creates a disposable service with MYSQL_DATABASE=nar_conversation_test.
The product does NOT execute migration SQL on startup or during normal requests.
"""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
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
    migrations = [
        Path("webgal_backend/migrations/002_nar_conversation_history.sql").read_text(),
        Path("webgal_backend/migrations/003_nar_conversation_pins.sql").read_text(),
    ]
    statements = "\n".join(
        line for migration in migrations for line in migration.splitlines()
        if not line.strip().startswith("--")
    ).split(";")
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

def test_conversation_management_is_persistent_and_owner_scoped(ledger):
    owner, other = "ci-" + uuid.uuid4().hex, "ci-" + uuid.uuid4().hex
    ids = [uuid.uuid4().hex for _ in range(2)]
    for cid in ids:
        turn, _ = ledger.start_turn(owner, cid, uuid.uuid4().hex, "测试历史菜单", "chat", create=True)
        ledger.fail_turn(owner, cid, turn["id"], "TEST")
    renamed = ledger.update_metadata(owner, ids[0], title="修改后的标题", pinned=True)
    assert renamed["title"] == "修改后的标题" and renamed["pinned"] is True
    assert ledger.list_conversations(owner)["items"][0]["id"] == ids[0]
    assert ledger.find_request(owner, ids[0], "nonexistent") is None
    with pytest.raises(ConversationMissing):
        ledger.update_metadata(other, ids[0], title="越权更新")
    with pytest.raises(ConversationMissing):
        ledger.delete_conversation(other, ids[0])
    assert ledger.delete_conversation(owner, ids[0]) == {"deleted": True}
    with pytest.raises(ConversationMissing):
        ledger.get_detail(owner, ids[0])
    assert ledger.list_conversations(owner)["items"][0]["id"] == ids[1]


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



def test_v2_pending_clarification_json_is_owner_scoped_and_cas_superseded(ledger):
    # Uses the existing public_metadata JSON column, no schema migration.
    from webgal_backend.nar_pending_v2 import make_clarification_metadata
    owner, other, cid = "ci-" + uuid.uuid4().hex, "ci-" + uuid.uuid4().hex, uuid.uuid4().hex
    clarification_id = uuid.uuid4().hex
    turn, _ = ledger.start_turn(owner, cid, uuid.uuid4().hex, "把那个居中", "chat", create=True)
    proposal = {"schema_version": "2.0", "tasks": [{
        "action": "revise", "target_relation": "ambiguous",
        "candidate_artifact_id": None, "desired_output": "unspecified",
        "goal": "把作品居中", "requirements": []}],
        "next_step": "clarify", "uncertainty": "target",
        "clarification": {
            "question": "你想修改哪件作品？",
            "options": ["马达动画", "函数网页"], "allow_custom": True}}
    metadata = make_clarification_metadata(
        proposal, origin_turn_id=turn["id"],
        verified_target_artifact_id=None, clarification_id=clarification_id)
    ledger.finish_turn(owner, cid, turn["id"], output="你想修改哪件作品？",
                       public_metadata=metadata)
    loaded = ledger.get_pending_clarification(owner, cid, clarification_id)
    assert loaded and loaded["metadata"]["choices"]["status"] == "pending"
    assert loaded["metadata"]["clarification_v2"]["origin_turn_id"] == turn["id"]
    assert ledger.get_detail(owner, cid)["messages"][-1]["metadata"]["choices"]["clarificationId"] == clarification_id
    with pytest.raises(ConversationMissing):
        ledger.get_pending_clarification(other, cid, clarification_id)
    assert ledger.supersede_pending_clarification(owner, cid) is True
    assert ledger.supersede_pending_clarification(owner, cid) is False
    assert ledger.get_pending_clarification(owner, cid) is None
    archived = ledger.get_pending_clarification(owner, cid, clarification_id)
    assert archived["metadata"]["clarification_v2"]["status"] == "superseded"
    assert archived["metadata"]["choices"]["status"] == "superseded"


def test_rpg_message_cas_is_owner_scoped_and_atomic_under_10_threads(ledger):
    """Real MySQL 8 CAS; only one concurrent confirmation can claim one card."""
    owner, cid = "ci-" + uuid.uuid4().hex, uuid.uuid4().hex
    turn, _ = ledger.start_turn(
        owner, cid, uuid.uuid4().hex,
        "《琵琶行》角色扮演三结局，不需要配音", "chat", create=True)
    initial = {"card_type": "rpg", "choices": {"question": "保持原有 metadata"},
               "timeline": [{"phase": "done"}], "billing": {"units": 1},
               "rpg": {"schema_version": 1, "state": "PREPARED", "spec_version": 1,
                       "spec": {"topic": "琵琶行", "source_ref": {"type": "origin_user_message"},
                                "duration_minutes": 20, "generate_images": True, "enable_voice": False},
                       "job_id": None, "confirmed_options": None,
                       "confirmed_hold_credits": None, "last_error_code": None}}
    ledger.finish_turn(owner, cid, turn["id"], output="已准备 RPG", public_metadata=initial)
    mid = ledger.get_detail(owner, cid)["messages"][-1]["id"]
    assert ledger.get_owned_rpg_message(owner, cid, mid)["original_prompt"].startswith("《琵琶行》")
    with pytest.raises(ConversationMissing):
        ledger.get_owned_rpg_message("ci-other-user", cid, mid)
    with pytest.raises(ConversationMissing):
        ledger.get_owned_rpg_message(owner, uuid.uuid4().hex, mid)
    selections = {"durationMinutes": 20, "generateImages": True, "enableVoice": False}

    def claim(_):
        return ledger.claim_rpg_message(owner, cid, mid, version=1,
                                        confirmed_options=selections, hold=70)

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(claim, range(10)))
    assert sum(results) == 1
    assert ledger.claim_rpg_message(owner, cid, mid, version=1,
                                    confirmed_options=selections, hold=70) is False
    card = ledger.get_owned_rpg_message(owner, cid, mid)["rpg"]
    assert card["state"] == "CLAIMED"
    assert card["confirmed_options"] == selections
    assert card["confirmed_hold_credits"] == 70
    job_id = uuid.uuid4().hex
    ledger.attach_rpg_job(owner, cid, mid, job_id)
    assert ledger.get_owned_rpg_message(owner, cid, mid)["rpg"]["job_id"] == job_id
    with pytest.raises(ConversationConflict):
        ledger.attach_rpg_job(owner, cid, mid, uuid.uuid4().hex)
    ledger.transition_rpg_message(owner, cid, mid, "JOB_CREATED", "STARTING")
    ledger.transition_rpg_message(owner, cid, mid, "STARTING", "STARTED")
    with pytest.raises(ConversationConflict):
        ledger.transition_rpg_message(owner, cid, mid, "JOB_CREATED", "STARTING")
    assert ledger.cancel_rpg_message(owner, cid, mid) is False
    metadata = ledger.get_detail(owner, cid)["messages"][-1]["metadata"]
    assert metadata["choices"] == initial["choices"]
    assert metadata["timeline"] == initial["timeline"]
    assert metadata["billing"] == initial["billing"]
    assert metadata["rpg"]["state"] == "STARTED"
    assert ledger.recent_rpg_games(owner, cid)[0]["id"] == job_id
    with pytest.raises(ConversationMissing):
        ledger.recent_rpg_games("ci-other-user", cid)


def test_rpg_job_binding_rejects_missing_json_null_path(ledger):
    """Existing job binding is immutable; missing JSON path is not treated as null."""
    owner, cid = "ci-" + uuid.uuid4().hex, uuid.uuid4().hex
    turn, _ = ledger.start_turn(
        owner, cid, uuid.uuid4().hex, "新 RPG", "chat", create=True)
    ledger.finish_turn(owner, cid, turn["id"], output="RPG",
                       public_metadata={"card_type": "rpg", "rpg": {
                           "state": "PREPARED", "spec_version": 1,
                           "spec": {"topic": "新 RPG"}, "job_id": None}})
    mid = ledger.get_detail(owner, cid)["messages"][-1]["id"]
    assert ledger.claim_rpg_message(
        owner, cid, mid, version=1,
        confirmed_options={"durationMinutes": 20, "generateImages": True, "enableVoice": False},
        hold=70)
    # The application always initializes JSON job_id=null. Simulate a broken
    # old row: it must fail closed instead of binding a second Job.
    with ledger._transaction() as db:
        db.execute("UPDATE nar_messages SET public_metadata = JSON_REMOVE("
                   "public_metadata, '$.rpg.job_id') WHERE id=%s", (mid,))
    with pytest.raises(ConversationConflict):
        ledger.attach_rpg_job(owner, cid, mid, uuid.uuid4().hex)
    assert ledger.get_owned_rpg_message(owner, cid, mid)["rpg"].get("job_id") is None


def test_rpg_clarification_preserves_exact_original_prompt_and_owner(ledger):
    owner, cid = "ci-" + uuid.uuid4().hex, uuid.uuid4().hex
    original = "《琵琶行》原文段落：\\nAAA BBB CCC。玩家必须扮演琵琶女，有三个结局。"
    first, _ = ledger.start_turn(
        owner, cid, uuid.uuid4().hex, original, "chat", create=True)
    ledger.finish_turn(owner, cid, first["id"], output="做哪种游戏？")
    second, _ = ledger.start_turn(
        owner, cid, uuid.uuid4().hex, "选择互动剧情游戏，不要配音", "chat")
    ledger.finish_turn(owner, cid, second["id"], output="请确认游戏",
                       public_metadata={"card_type": "rpg", "rpg": {
                           "state": "PREPARED", "spec_version": 1,
                           "spec": {"topic": "琵琶行", "duration_minutes": 20,
                                    "generate_images": True, "enable_voice": False},
                           "job_id": None, "source_turn_id": first["id"]}})
    mid = ledger.get_detail(owner, cid)["messages"][-1]["id"]
    card = ledger.get_owned_rpg_message(owner, cid, mid)
    assert original in card["original_prompt"]
    assert "选择互动剧情游戏" in card["original_prompt"]
    assert ledger.get_turn_original_prompt(owner, cid, first["id"]) == original
    with pytest.raises(ConversationMissing):
        ledger.get_turn_original_prompt("ci-another-user", cid, first["id"])
    with pytest.raises(ConversationMissing):
        ledger.get_turn_original_prompt(owner, cid, "f" * 32)
    with pytest.raises(ConversationMissing):
        ledger.get_owned_rpg_message("ci-another-user", cid, mid)


def test_rpg_edit_references_ignore_newer_unconfirmed_cards(ledger):
    owner, cid = "ci-" + uuid.uuid4().hex, uuid.uuid4().hex
    created, _ = ledger.start_turn(owner, cid, uuid.uuid4().hex, "成品剧情游戏", "chat", create=True)
    job_id = uuid.uuid4().hex
    ledger.finish_turn(owner, cid, created["id"], output="已开始",
                       public_metadata={"card_type": "rpg", "rpg": {
                           "state": "STARTED", "spec_version": 1,
                           "spec": {"topic": "已完成旧游戏"}, "job_id": job_id}})
    for i in range(7):
        pending, _ = ledger.start_turn(owner, cid, uuid.uuid4().hex,
                                       f"未确认游戏 {i}", "chat")
        ledger.finish_turn(owner, cid, pending["id"], output="待确认",
                           public_metadata={"card_type": "rpg", "rpg": {
                               "state": "PREPARED", "spec_version": 1,
                               "spec": {"topic": f"未确认 {i}"}, "job_id": None}})
    games = ledger.recent_rpg_games(owner, cid, limit=5)
    assert len(games) == 1 and games[0]["id"] == job_id
    assert games[0]["title"] == "已完成旧游戏"
