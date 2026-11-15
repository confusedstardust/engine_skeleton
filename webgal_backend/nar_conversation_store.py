"""MySQL-backed, owner-scoped NarAgent conversation ledger.

Uses the established Forge database_transaction() with no startup schema DDL.
Every mutating method is transactional. State transitions are idempotent; a
network-uncertain NarAgent dispatch is never blindly repeated.
"""
from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime
from typing import Any

from .database import database_transaction
from .nar_choice_protocol import normalize_agent_choice


ACTIVE = ("QUEUED", "RUNNING", "UNKNOWN")
FINAL = ("SUCCEEDED", "FAILED")


class ConversationConflict(ValueError):
    pass


class ConversationMissing(LookupError):
    pass


def _id() -> str:
    return uuid.uuid4().hex


def _time(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat(timespec="microseconds") + ("Z" if isinstance(value, datetime) else "")


def _encode_cursor(row: dict, *keys: str) -> str:
    data = [str(row[k]) if row[k] is not None else "" for k in keys]
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")


def _decode_cursor(token: str | None, count: int) -> list[str] | None:
    if not token:
        return None
    if len(token) > 512:
        raise ValueError("Invalid page cursor")
    try:
        obj = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
        if not isinstance(obj, list) or len(obj) != count or not all(
            isinstance(item, str) and len(item) <= 100 for item in obj
        ):
            raise ValueError
        return obj
    except (ValueError, TypeError, UnicodeDecodeError):
        raise ValueError("Invalid page cursor") from None


def _conversation(row: dict) -> dict:
    return {"id": row["id"], "title": row["title"], "pinned": bool(row.get("is_pinned", 0)),
            "createdAt": _time(row["created_at"]), "activeAt": _time(row["active_at"])}


def _message(row: dict) -> dict:
    raw = row.get("public_metadata")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = None
    metadata = dict(raw) if isinstance(raw, dict) else {}
    content = row["content"]
    if row["role"] == "assistant":
        content, choice = normalize_agent_choice(content)
        if choice and "choices" not in metadata:
            metadata["choices"] = choice
    return {"id": row["id"], "seq": row["seq"], "role": row["role"],
            "content": content, "createdAt": _time(row["created_at"]),
            "metadata": metadata or None}


def _turn(row: dict) -> dict:
    return {"id": row["id"], "conversationId": row["conversation_id"],
            "status": row["status"], "mode": row["mode"],
            "runId": row.get("agent_run_id"), "errorCode": row.get("error_code"),
            "parentArtifactId": row.get("parent_artifact_id"),
            "createdAt": _time(row["created_at"])}


def _artifact(row: dict) -> dict:
    return {"artifactId": row["artifact_id"], "conversationId": row["conversation_id"],
            "originMessageId": row.get("origin_message_id"),
            "workId": row.get("work_id"), "title": row["title"],
            "kind": row["kind"], "createdAt": _time(row["created_at"])}


class NarConversationStore:
    def __init__(self, transaction=database_transaction):
        self._transaction = transaction

    def ready(self) -> bool:
        try:
            with self._transaction() as db:
                for name in ("nar_conversations", "nar_messages", "nar_turns",
                             "nar_turn_dispatches", "nar_conversation_artifacts"):
                    db.execute("SELECT 1 FROM " + name + " LIMIT 0")
                # Pinning requires the additive 003 migration as well.
                db.execute("SELECT is_pinned FROM nar_conversations LIMIT 0")
            return True
        except Exception:
            return False

    @staticmethod
    def _own(db, owner: str, cid: str, *, lock: bool = False) -> dict:
        db.execute("SELECT * FROM nar_conversations WHERE id=%s AND owner_id=%s" +
                   (" FOR UPDATE" if lock else ""), (cid, owner))
        row = db.fetchone()
        if row is None:
            raise ConversationMissing("Conversation not found")
        return row

    @staticmethod
    def _get_turn(db, cid: str, tid: str, *, lock: bool = False) -> dict:
        db.execute("SELECT * FROM nar_turns WHERE id=%s AND conversation_id=%s" +
                   (" FOR UPDATE" if lock else ""), (tid, cid))
        row = db.fetchone()
        if row is None:
            raise ConversationMissing("Turn not found")
        return row

    def list_conversations(self, owner: str, limit: int = 30, cursor: str | None = None) -> dict:
        position = _decode_cursor(cursor, 3)
        with self._transaction() as db:
            params: list[Any] = [owner]
            q = "SELECT * FROM nar_conversations WHERE owner_id=%s"
            if position:
                q += " AND (is_pinned,active_at,id)<(%s,%s,%s)"
                params.extend(position)
            q += " ORDER BY is_pinned DESC,active_at DESC,id DESC LIMIT %s"
            params.append(limit + 1)
            db.execute(q, tuple(params))
            rows = list(db.fetchall())
        has_more = len(rows) > limit
        rows = rows[:limit]
        return {"items": [_conversation(r) for r in rows],
                "nextCursor": _encode_cursor(rows[-1], "is_pinned", "active_at", "id")
                if rows and has_more else None}

    def update_metadata(self, owner: str, cid: str, *, title: str | None = None,
                        pinned: bool | None = None) -> dict:
        if title is None and pinned is None:
            raise ValueError("No updates provided")
        updates, params = [], []
        if title is not None:
            title = title.strip()
            if not title or len(title) > 160:
                raise ValueError("Invalid title")
            updates.append("title=%s")
            params.append(title)
        if pinned is not None:
            updates.append("is_pinned=%s")
            params.append(bool(pinned))
        with self._transaction() as db:
            self._own(db, owner, cid, lock=True)
            db.execute("UPDATE nar_conversations SET " + ",".join(updates)
                       + " WHERE id=%s AND owner_id=%s", tuple([*params, cid, owner]))
            return _conversation(self._own(db, owner, cid))

    def delete_conversation(self, owner: str, cid: str) -> dict:
        with self._transaction() as db:
            self._own(db, owner, cid, lock=True)
            db.execute("SELECT id FROM nar_turns WHERE conversation_id=%s AND status IN "
                       "('QUEUED','RUNNING','UNKNOWN') LIMIT 1", (cid,))
            if db.fetchone():
                raise ConversationConflict("Cannot delete an active conversation")
            # Explicit child deletion avoids MySQL's cross-table cascade cycle:
            # turns reference prompt messages, while both reference conversations.
            # Saved works live independently and are never removed here.
            db.execute("DELETE FROM nar_conversation_artifacts WHERE conversation_id=%s", (cid,))
            db.execute("DELETE FROM nar_turns WHERE conversation_id=%s", (cid,))
            db.execute("DELETE FROM nar_messages WHERE conversation_id=%s", (cid,))
            db.execute("DELETE FROM nar_conversations WHERE id=%s AND owner_id=%s", (cid, owner))
        return {"deleted": True}

    def find_request(self, owner: str, cid: str, request_id: str) -> dict | None:
        """Resolve the original concrete execution mode before retrying an auto-routed turn."""
        with self._transaction() as db:
            db.execute("SELECT t.*,m.content AS stored_prompt FROM nar_turns t "
                       "JOIN nar_messages m ON m.id=t.prompt_message_id "
                       "JOIN nar_conversations c ON c.id=t.conversation_id "
                       "WHERE t.conversation_id=%s AND t.client_request_id=%s AND c.owner_id=%s",
                       (cid, request_id, owner))
            row = db.fetchone()
        return {**_turn(row), "prompt": row["stored_prompt"]} if row else None

    def get_messages(self, owner: str, cid: str, before: int | None = None, limit: int = 30) -> dict:
        with self._transaction() as db:
            self._own(db, owner, cid)
            params: list[Any] = [cid]
            query = "SELECT * FROM nar_messages WHERE conversation_id=%s"
            if before is not None:
                query += " AND seq<%s"
                params.append(before)
            query += " ORDER BY seq DESC LIMIT %s"
            params.append(limit + 1)
            db.execute(query, tuple(params))
            rows = list(db.fetchall())
        more = len(rows) > limit
        rows = rows[:limit]
        return {"items": [_message(r) for r in reversed(rows)],
                "nextBefore": rows[-1]["seq"] if rows and more else None}

    def get_detail(self, owner: str, cid: str) -> dict:
        with self._transaction() as db:
            current = self._own(db, owner, cid)
            db.execute("SELECT * FROM nar_turns WHERE conversation_id=%s AND status IN "
                       "('QUEUED','RUNNING','UNKNOWN') ORDER BY created_at DESC LIMIT 1", (cid,))
            current_turn = db.fetchone()
            db.execute("SELECT * FROM nar_conversation_artifacts WHERE conversation_id=%s "
                       "ORDER BY created_at DESC LIMIT 100", (cid,))
            artifacts = list(db.fetchall())
        messages = self.get_messages(owner, cid)
        return {"conversation": _conversation(current), "messages": messages["items"],
                "nextBefore": messages["nextBefore"],
                "activeTurn": _turn(current_turn) if current_turn else None,
                "artifacts": [_artifact(a) for a in artifacts]}

    def start_turn(self, owner: str, cid: str, request_id: str, prompt: str, mode: str,
                   parent_artifact_id: str | None = None, *, create: bool = False) -> tuple[dict, bool]:
        with self._transaction() as db:
            if create:
                db.execute("INSERT IGNORE INTO nar_conversations (id,owner_id,title) VALUES (%s,%s,%s)",
                           (cid, owner, prompt.strip()[:160]))
            self._own(db, owner, cid, lock=True)
            db.execute("SELECT t.*, m.content AS stored_prompt FROM nar_turns t "
                       "JOIN nar_messages m ON m.id=t.prompt_message_id "
                       "WHERE t.conversation_id=%s AND t.client_request_id=%s",
                       (cid, request_id))
            existing = db.fetchone()
            if existing:
                if (existing["stored_prompt"] != prompt or existing["mode"] != mode
                        or existing["parent_artifact_id"] != parent_artifact_id):
                    raise ConversationConflict("Idempotency key already belongs to another request")
                return _turn(existing), False
            db.execute("SELECT id FROM nar_turns WHERE conversation_id=%s AND status IN "
                       "('QUEUED','RUNNING','UNKNOWN') LIMIT 1", (cid,))
            if db.fetchone():
                raise ConversationConflict("已有生成任务正在进行或等待确认")
            db.execute("SELECT COALESCE(MAX(seq),0) AS last_seq FROM nar_messages WHERE conversation_id=%s",
                       (cid,))
            seq = int(db.fetchone()["last_seq"]) + 1
            mid, tid = _id(), _id()
            db.execute("INSERT INTO nar_messages (id,conversation_id,seq,role,content,turn_id) "
                       "VALUES (%s,%s,%s,'user',%s,%s)", (mid, cid, seq, prompt, tid))
            db.execute("INSERT INTO nar_turns "
                       "(id,conversation_id,client_request_id,prompt_message_id,mode,parent_artifact_id) "
                       "VALUES (%s,%s,%s,%s,%s,%s)",
                       (tid, cid, request_id, mid, mode, parent_artifact_id))
            db.execute("INSERT INTO nar_turn_dispatches (turn_id,state) VALUES (%s,'PENDING')", (tid,))
            db.execute("UPDATE nar_conversations SET active_at=CURRENT_TIMESTAMP(6) WHERE id=%s", (cid,))
            db.execute("SELECT * FROM nar_turns WHERE id=%s", (tid,))
            return _turn(db.fetchone()), True

    def model_history(self, owner: str, cid: str, tid: str) -> list[dict]:
        with self._transaction() as db:
            self._own(db, owner, cid)
            turn = self._get_turn(db, cid, tid)
            db.execute("SELECT content FROM nar_messages WHERE id=%s", (turn["prompt_message_id"],))
            prompt_row = db.fetchone()
            remaining_budget = max(0, 36000 - len(prompt_row["content"])) if prompt_row else 0
            db.execute("SELECT m.role,m.content FROM nar_messages m "
                       "JOIN nar_messages prompt ON prompt.id=%s "
                       "WHERE m.conversation_id=%s AND m.seq<prompt.seq "
                       "ORDER BY m.seq DESC LIMIT 20", (turn["prompt_message_id"], cid))
            rows = list(db.fetchall())
        selected = []
        budget = remaining_budget
        for row in rows:
            if len(row["content"]) > 12000 or len(row["content"]) > budget:
                break
            budget -= len(row["content"])
            selected.append({"role": row["role"], "content": row["content"]})
        return list(reversed(selected))

    def mark_running(self, owner: str, cid: str, tid: str, run_id: str) -> dict:
        with self._transaction() as db:
            self._own(db, owner, cid, lock=True)
            turn = self._get_turn(db, cid, tid, lock=True)
            if turn["status"] not in ("QUEUED", "RUNNING"):
                return _turn(turn)
            db.execute("UPDATE nar_turns SET status='RUNNING',agent_run_id=%s,"
                       "updated_at=CURRENT_TIMESTAMP(6) WHERE id=%s", (run_id, tid))
            db.execute("UPDATE nar_turn_dispatches SET state='ACKNOWLEDGED',"
                       "acknowledged_at=CURRENT_TIMESTAMP(6) WHERE turn_id=%s", (tid,))
            return {**_turn(turn), "status": "RUNNING", "runId": run_id}

    def finish_turn(self, owner: str, cid: str, tid: str, *, output: str,
                    artifact_id: str | None = None, title: str | None = None,
                    kind: str = "html", run_id: str | None = None,
                    public_metadata: dict | None = None) -> dict:
        with self._transaction() as db:
            self._own(db, owner, cid, lock=True)
            turn = self._get_turn(db, cid, tid, lock=True)
            if turn["status"] in FINAL:
                return _turn(turn)
            mid = _id()
            db.execute("SELECT COALESCE(MAX(seq),0) AS last_seq FROM nar_messages WHERE conversation_id=%s",
                       (cid,))
            seq = int(db.fetchone()["last_seq"]) + 1
            body = output
            metadata_values = dict(public_metadata or {})
            if not artifact_id:
                body, choice = normalize_agent_choice(output)
                if choice:
                    metadata_values["choices"] = choice
            metadata = json.dumps(metadata_values, ensure_ascii=False) if metadata_values else None
            db.execute("INSERT INTO nar_messages "
                       "(id,conversation_id,seq,role,content,turn_id,public_metadata) "
                       "VALUES (%s,%s,%s,'assistant',%s,%s,%s)",
                       (mid, cid, seq, body[:12000] or ("请选择下一步操作。" if not artifact_id else "作品已生成，可以查看预览。"), tid, metadata))
            if artifact_id:
                db.execute("INSERT INTO nar_conversation_artifacts "
                           "(conversation_id,artifact_id,origin_message_id,title,kind) "
                           "VALUES (%s,%s,%s,%s,%s) "
                           "ON DUPLICATE KEY UPDATE origin_message_id=VALUES(origin_message_id)",
                           (cid, artifact_id, mid, (title or "互动学习作品")[:160], kind))
            db.execute("UPDATE nar_turns SET status='SUCCEEDED',agent_run_id=COALESCE(%s,agent_run_id),"
                       "updated_at=CURRENT_TIMESTAMP(6),finished_at=CURRENT_TIMESTAMP(6) WHERE id=%s",
                       (run_id, tid))
            db.execute("UPDATE nar_turn_dispatches SET state='FINISHED' WHERE turn_id=%s", (tid,))
            db.execute("UPDATE nar_conversations SET active_at=CURRENT_TIMESTAMP(6) WHERE id=%s", (cid,))
            return {**_turn(turn), "status": "SUCCEEDED", "runId": run_id or turn.get("agent_run_id")}

    def fail_turn(self, owner: str, cid: str, tid: str, code: str, *, uncertain: bool = False,
                  public_error: str | None = None, phase: str | None = None,
                  public_metadata: dict | None = None) -> dict:
        """Persist a safe public failure reply in the SAME transaction as the turn.

        No schema changes: metadata uses existing nar_messages.public_metadata.
        Retried status checks cannot duplicate the reply after terminal failure.
        """
        status = "UNKNOWN" if uncertain else "FAILED"
        safe_code = code[:80]
        safe_phase = phase if phase in (
            "DESIGNING", "PLANNING", "DRAFTING", "BUILDING", "CHECKING", "FINALIZING"
        ) else None
        with self._transaction() as db:
            self._own(db, owner, cid, lock=True)
            turn = self._get_turn(db, cid, tid, lock=True)
            if turn["status"] in FINAL or (turn["status"] == "UNKNOWN" and uncertain):
                return _turn(turn)
            if public_error:
                db.execute("SELECT COALESCE(MAX(seq),0) AS last_seq FROM nar_messages WHERE conversation_id=%s",
                           (cid,))
                seq = int(db.fetchone()["last_seq"]) + 1
                # This text comes from our NarAgent's PUBLIC error string only.
                # Never include provider exception bodies or stack traces.
                message = public_error.strip()[:240]
                detail = ["错误码：" + safe_code]
                if safe_phase:
                    detail.insert(0, "阶段：" + safe_phase)
                if turn.get("agent_run_id"):
                    detail.append("任务编号：" + str(turn["agent_run_id"])[:80])
                message += "（" + " · ".join(detail) + "）"
                info = json.dumps({"errorCode": safe_code, "phase": safe_phase,
                                   **(public_metadata or {})},
                                  ensure_ascii=False)
                db.execute("INSERT INTO nar_messages "
                           "(id,conversation_id,seq,role,content,turn_id,public_metadata) "
                           "VALUES (%s,%s,%s,'assistant',%s,%s,%s)",
                           (_id(), cid, seq, message, tid, info))
            db.execute("UPDATE nar_turns SET status=%s,error_code=%s,"
                       "updated_at=CURRENT_TIMESTAMP(6),"
                       "finished_at=IF(%s,CURRENT_TIMESTAMP(6),NULL) WHERE id=%s",
                       (status, safe_code, not uncertain, tid))
            db.execute("UPDATE nar_turn_dispatches SET state=%s WHERE turn_id=%s",
                       ("UNCERTAIN" if uncertain else "FINISHED", tid))
            return {**_turn(turn), "status": status, "errorCode": safe_code}

    def get_turn(self, owner: str, cid: str, tid: str) -> dict:
        with self._transaction() as db:
            self._own(db, owner, cid)
            return _turn(self._get_turn(db, cid, tid))

    def link_work(self, owner: str, cid: str, artifact_id: str, work_id: str) -> None:
        with self._transaction() as db:
            self._own(db, owner, cid, lock=True)
            db.execute("SELECT work_id FROM nar_conversation_artifacts "
                       "WHERE conversation_id=%s AND artifact_id=%s FOR UPDATE",
                       (cid, artifact_id))
            existing = db.fetchone()
            if existing is None:
                raise ConversationMissing("Artifact not in conversation")
            if existing["work_id"] == work_id:
                return
            if existing["work_id"] and existing["work_id"] != work_id:
                raise ConversationConflict("Artifact is already linked to a different work")
            db.execute("UPDATE nar_conversation_artifacts SET work_id=%s "
                       "WHERE conversation_id=%s AND artifact_id=%s", (work_id, cid, artifact_id))

    def artifact_history(self, owner: str, limit: int = 30, cursor: str | None = None) -> dict:
        """One artifact row per identifier with all owner-verified conversation sources."""
        position = _decode_cursor(cursor, 2)
        with self._transaction() as db:
            # Page unique artifacts, not association rows: a single artifact can
            # be produced/referenced in several conversations.
            q = ("SELECT a.artifact_id, MAX(a.created_at) AS latest_at "
                 "FROM nar_conversation_artifacts a "
                 "JOIN nar_conversations c ON c.id=a.conversation_id "
                 "WHERE c.owner_id=%s GROUP BY a.artifact_id")
            params: list[Any] = [owner]
            if position:
                q += " HAVING (MAX(a.created_at),a.artifact_id)<(%s,%s)"
                params.extend(position)
            q += " ORDER BY latest_at DESC,a.artifact_id DESC LIMIT %s"
            params.append(limit + 1)
            db.execute(q, tuple(params))
            page = list(db.fetchall())
            more = len(page) > limit
            page = page[:limit]
            if not page:
                return {"items": [], "nextCursor": None}
            placeholders = ",".join(["%s"] * len(page))
            db.execute(
                "SELECT a.*,c.title AS session_title "
                "FROM nar_conversation_artifacts a "
                "JOIN nar_conversations c ON c.id=a.conversation_id "
                "WHERE c.owner_id=%s AND a.artifact_id IN (" + placeholders + ") "
                "ORDER BY a.created_at DESC,a.conversation_id DESC",
                (owner, *(p["artifact_id"] for p in page)),
            )
            sources = list(db.fetchall())
        grouped: dict[str, dict] = {}
        for row in sources:
            artifact = grouped.get(row["artifact_id"])
            if not artifact:
                artifact = {**_artifact(row), "sources": []}
                grouped[row["artifact_id"]] = artifact
            artifact["sources"].append({
                "conversationId": row["conversation_id"],
                "title": row["session_title"],
            })
        cursor_row = {"created_at": page[-1]["latest_at"],
                      "artifact_id": page[-1]["artifact_id"]}
        return {"items": [grouped[p["artifact_id"]] for p in page],
                "nextCursor": _encode_cursor(cursor_row, "created_at", "artifact_id")
                if more else None}
