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
from .nar_pending_v2 import (validate_clarification_answer,
                             mark_clarification_answered)


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

    def latest_artifact(self, owner: str, cid: str, selected_id: str | None = None) -> dict | None:
        """Fetch an artifact in this owner's conversation; selection wins over recency."""
        with self._transaction() as db:
            self._own(db, owner, cid)
            query = ("SELECT artifact_id, kind FROM nar_conversation_artifacts "
                     "WHERE conversation_id=%s")
            params = (cid,)
            if selected_id:
                query += " AND artifact_id=%s"
                params = (cid, selected_id)
            query += " ORDER BY created_at DESC, artifact_id DESC LIMIT 1"
            db.execute(query, params)
            row = db.fetchone()
            return {"artifactId": row["artifact_id"], "kind": row["kind"]} if row else None

    def artifact_candidates(self, owner: str, cid: str,
                            selected_id: str | None = None, limit: int = 5) -> list[dict]:
        """Owner + conversation scoped candidates; never choose recency as edit target.

        An explicit old selection remains in the candidate set so references
        can be resolved without widening the model's available artifact IDs.
        """
        if not 1 <= limit <= 5:
            raise ValueError("Invalid artifact candidate limit")
        with self._transaction() as db:
            self._own(db, owner, cid)
            chosen = None
            if selected_id:
                db.execute("SELECT artifact_id, kind, title FROM nar_conversation_artifacts "
                           "WHERE conversation_id=%s AND artifact_id=%s",
                           (cid, selected_id))
                chosen = db.fetchone()
                if not chosen:
                    raise ConversationMissing("Selected artifact is not in this conversation")
            db.execute("SELECT artifact_id, kind, title FROM nar_conversation_artifacts "
                       "WHERE conversation_id=%s ORDER BY created_at DESC, artifact_id DESC LIMIT %s",
                       (cid, limit))
            recent = list(db.fetchall())
        rows = ([chosen] if chosen else []) + recent
        unique = []
        seen = set()
        for row in rows:
            if row["artifact_id"] not in seen and len(unique) < limit:
                seen.add(row["artifact_id"])
                unique.append({"artifactId": row["artifact_id"], "kind": row["kind"],
                               "title": row["title"]})
        return unique

    def get_pending_clarification(self, owner: str, cid: str,
                                  clarification_id: str | None = None) -> dict | None:
        """Owner-scoped pending metadata, including the original task proposal."""
        if clarification_id is not None and (len(clarification_id) != 32
               or any(c not in "0123456789abcdef" for c in clarification_id)):
            raise ValueError("Invalid clarification ID")
        with self._transaction() as db:
            self._own(db, owner, cid)
            where = ("JSON_UNQUOTE(JSON_EXTRACT(public_metadata,"
                     "'$.clarification_v2.clarification_id'))=%s"
                     if clarification_id else
                     "JSON_UNQUOTE(JSON_EXTRACT(public_metadata,"
                     "'$.clarification_v2.status'))='pending'")
            args = (cid, clarification_id) if clarification_id else (cid,)
            db.execute("SELECT id, public_metadata FROM nar_messages "
                       "WHERE conversation_id=%s AND role='assistant' AND " + where +
                       " ORDER BY seq DESC LIMIT 1", args)
            row = db.fetchone()
        if not row:
            return None
        metadata = row["public_metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        if not isinstance(metadata, dict):
            return None
        return {"message_id": row["id"], "metadata": metadata}

    def claim_clarification_answer(self, owner: str, cid: str, request_id: str,
                                   raw_answer: dict) -> dict:
        """Atomically bind a user answer to the originating pending task.

        A separate submit_turn path must use the SAME request_id for dispatch;
        this method never runs an agent or reserves credits.
        """
        from .nar_pending_schema_v2 import ClarificationAnswer
        answer = ClarificationAnswer.model_validate(raw_answer)
        with self._transaction() as db:
            self._own(db, owner, cid, lock=True)
            db.execute("SELECT id, public_metadata FROM nar_messages "
                       "WHERE conversation_id=%s AND role='assistant' AND "
                       "JSON_UNQUOTE(JSON_EXTRACT(public_metadata,"
                       "'$.clarification_v2.clarification_id'))=%s "
                       "ORDER BY seq DESC LIMIT 1 FOR UPDATE",
                       (cid, answer.clarification_id))
            row = db.fetchone()
            if not row:
                raise ConversationMissing("Clarification does not belong to conversation")
            metadata = row["public_metadata"]
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            if not isinstance(metadata, dict):
                raise ValueError("Invalid clarification state")
            info = metadata.get("clarification_v2") or {}
            if info.get("status") == "answered":
                if info.get("answered_request_id") == request_id:
                    return {"metadata": metadata, "reused": True}
                raise ConversationConflict("Clarification was already answered")
            validated = validate_clarification_answer(metadata, answer)
            updated = mark_clarification_answered(metadata, validated, request_id)
            db.execute("UPDATE nar_messages SET public_metadata=%s WHERE id=%s "
                       "AND conversation_id=%s AND "
                       "JSON_UNQUOTE(JSON_EXTRACT(public_metadata,"
                       "'$.clarification_v2.status'))='pending'",
                       (json.dumps(updated, ensure_ascii=False), row["id"], cid))
            if db.rowcount != 1:
                raise ConversationConflict("Clarification changed while answering")
            return {"metadata": updated, "reused": False}

    def supersede_pending_clarification(self, owner: str, cid: str) -> bool:
        """An explicit unrelated new task may supersede the latest pending one."""
        with self._transaction() as db:
            self._own(db, owner, cid, lock=True)
            db.execute("SELECT id, public_metadata FROM nar_messages "
                       "WHERE conversation_id=%s AND role='assistant' AND "
                       "JSON_UNQUOTE(JSON_EXTRACT(public_metadata,"
                       "'$.clarification_v2.status'))='pending' "
                       "ORDER BY seq DESC LIMIT 1 FOR UPDATE", (cid,))
            row = db.fetchone()
            if not row:
                return False
            metadata = row["public_metadata"]
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            if not isinstance(metadata, dict):
                raise ValueError("Invalid clarification state")
            for key in ("choices", "clarification_v2", "pending_task_v2"):
                if not isinstance(metadata.get(key), dict):
                    raise ValueError("Invalid pending task metadata")
                metadata[key]["status"] = "superseded"
            db.execute("UPDATE nar_messages SET public_metadata=%s WHERE id=%s "
                       "AND conversation_id=%s AND "
                       "JSON_UNQUOTE(JSON_EXTRACT(public_metadata,"
                       "'$.clarification_v2.status'))='pending'",
                       (json.dumps(metadata, ensure_ascii=False), row["id"], cid))
            if db.rowcount != 1:
                raise ConversationConflict("Pending clarification changed")
            return True

    def recent_rpg_games(self, owner: str, cid: str, limit: int = 5) -> list[dict]:
        """Owner-scoped intent references; verify actual WebGAL owner before edit links."""
        with self._transaction() as db:
            self._own(db, owner, cid)
            db.execute(
                "SELECT public_metadata FROM nar_messages "
                "WHERE conversation_id=%s AND role='assistant' "
                "AND JSON_UNQUOTE(JSON_EXTRACT(public_metadata,'$.card_type'))='rpg' "
                "AND JSON_TYPE(JSON_EXTRACT(public_metadata,'$.rpg.job_id'))='STRING' "
                "ORDER BY seq DESC LIMIT %s", (cid, min(max(limit, 1), 20)))
            rows = list(db.fetchall())
        games = []
        for row in rows:
            metadata = row["public_metadata"]
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except ValueError:
                    continue
            if not isinstance(metadata, dict):
                continue
            rpg = metadata.get("rpg")
            if not isinstance(rpg, dict):
                continue
            job_id = rpg.get("job_id")
            if not isinstance(job_id, str) or len(job_id) != 32 or any(
                char not in "0123456789abcdef" for char in job_id
            ):
                continue
            spec = rpg.get("spec")
            games.append({"id": job_id,
                          "title": str((spec if isinstance(spec, dict) else {}).get("topic") or "")[:200],
                          "status": str(rpg.get("state") or "created")[:32]})
            if len(games) >= limit:
                break
        return games

    def get_turn_original_prompt(self, owner: str, cid: str, tid: str) -> str:
        """Resolve a previous clarification's exact user text, not LLM summary."""
        if not isinstance(tid, str) or len(tid) != 32 or any(
            ch not in "0123456789abcdef" for ch in tid
        ):
            raise ConversationMissing("Invalid origin turn")
        with self._transaction() as db:
            self._own(db, owner, cid)
            db.execute(
                "SELECT m.content FROM nar_turns t "
                "JOIN nar_messages m ON m.id=t.prompt_message_id "
                "WHERE t.id=%s AND t.conversation_id=%s AND m.conversation_id=%s "
                "AND m.role='user' LIMIT 1", (tid, cid, cid))
            row = db.fetchone()
        if not row:
            raise ConversationMissing("Origin turn does not belong to this conversation")
        return row["content"]

    def get_owned_rpg_message(self, owner: str, cid: str, message_id: str) -> dict:
        """Return owner-verified card and origin prompt; never expose origin via public API."""
        with self._transaction() as db:
            db.execute(
                "SELECT m.public_metadata, m.turn_id, origin.content AS origin_prompt "
                "FROM nar_messages m "
                "JOIN nar_conversations c ON c.id=m.conversation_id "
                "JOIN nar_turns t ON t.id=m.turn_id AND t.conversation_id=c.id "
                "JOIN nar_messages origin ON origin.id=t.prompt_message_id "
                "WHERE c.owner_id=%s AND c.id=%s AND m.id=%s "
                "AND m.role='assistant' AND "
                "JSON_UNQUOTE(JSON_EXTRACT(m.public_metadata,'$.card_type'))='rpg'",
                (owner, cid, message_id))
            row = db.fetchone()
        if not row:
            raise ConversationMissing("RPG card does not belong to this owner and conversation")
        metadata = row["public_metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        if not isinstance(metadata, dict) or not isinstance(metadata.get("rpg"), dict):
            raise ConversationMissing("Malformed RPG card")
        source_prompt = row["origin_prompt"]
        source_turn_id = metadata["rpg"].get("source_turn_id")
        if source_turn_id:
            # A follow-up like "option 1" is not the complete creative input.
            # Resolve the ORIGINAL, owner-scoped user message at confirm time.
            previous_prompt = self.get_turn_original_prompt(owner, cid, source_turn_id)
            if source_turn_id != row["turn_id"]:
                source_prompt = (
                    "原始创作要求和材料：\n" + previous_prompt +
                    "\n随后用户的选择或补充：\n" + source_prompt
                )
        return {"message_id": message_id, "turn_id": row["turn_id"],
                "rpg": metadata["rpg"], "original_prompt": source_prompt}

    def claim_rpg_message(self, owner: str, cid: str, message_id: str, *,
                          version: int, confirmed_options: dict, hold: int) -> bool:
        """Single MySQL compare-and-swap; ONLY winner may call WebGAL create/run."""
        options_json = json.dumps(confirmed_options, ensure_ascii=False)
        with self._transaction() as db:
            db.execute(
                "UPDATE nar_messages m JOIN nar_conversations c ON c.id=m.conversation_id "
                "SET m.public_metadata=JSON_SET(m.public_metadata,"
                "'$.rpg.state','CLAIMED',"
                "'$.rpg.confirmed_options',CAST(%s AS JSON),"
                "'$.rpg.confirmed_hold_credits',%s) "
                "WHERE m.id=%s AND m.conversation_id=%s AND m.role='assistant' "
                "AND c.owner_id=%s "
                "AND JSON_UNQUOTE(JSON_EXTRACT(m.public_metadata,'$.card_type'))='rpg' "
                "AND JSON_UNQUOTE(JSON_EXTRACT(m.public_metadata,'$.rpg.state'))='PREPARED' "
                "AND CAST(JSON_UNQUOTE(JSON_EXTRACT(m.public_metadata,"
                "'$.rpg.spec_version')) AS UNSIGNED)=%s",
                (options_json, hold, message_id, cid, owner, version))
            return db.rowcount == 1

    def attach_rpg_job(self, owner: str, cid: str, message_id: str, job_id: str) -> None:
        """Persist actual Job ID BEFORE calling run, never overwrite an existing ID."""
        with self._transaction() as db:
            db.execute(
                "UPDATE nar_messages m JOIN nar_conversations c ON c.id=m.conversation_id "
                "SET m.public_metadata=JSON_SET(m.public_metadata,"
                "'$.rpg.job_id',%s,'$.rpg.state','JOB_CREATED') "
                "WHERE m.id=%s AND m.conversation_id=%s AND m.role='assistant' "
                "AND c.owner_id=%s "
                "AND JSON_UNQUOTE(JSON_EXTRACT(m.public_metadata,'$.card_type'))='rpg' "
                "AND JSON_UNQUOTE(JSON_EXTRACT(m.public_metadata,'$.rpg.state'))='CLAIMED' "
                "AND JSON_TYPE(JSON_EXTRACT(m.public_metadata,'$.rpg.job_id'))='NULL'",
                (job_id, message_id, cid, owner))
            if db.rowcount != 1:
                raise ConversationConflict("RPG job binding is not in CLAIMED state")

    def transition_rpg_message(self, owner: str, cid: str, message_id: str,
                               expected_state: str, state: str, error_code: str | None = None) -> None:
        """Update only RPG JSON paths, preserving choices/billing/timeline."""
        with self._transaction() as db:
            db.execute(
                "UPDATE nar_messages m JOIN nar_conversations c ON c.id=m.conversation_id "
                "SET m.public_metadata=JSON_SET(m.public_metadata,"
                "'$.rpg.state',%s,'$.rpg.last_error_code',%s) "
                "WHERE m.id=%s AND m.conversation_id=%s AND m.role='assistant' "
                "AND c.owner_id=%s "
                "AND JSON_UNQUOTE(JSON_EXTRACT(m.public_metadata,'$.card_type'))='rpg' "
                "AND JSON_UNQUOTE(JSON_EXTRACT(m.public_metadata,'$.rpg.state'))=%s",
                (state, error_code, message_id, cid, owner, expected_state))
            if db.rowcount != 1:
                raise ConversationConflict("RPG card state changed")

    def cancel_rpg_message(self, owner: str, cid: str, message_id: str) -> bool:
        """Cancel only PREPARED cards; never pretend to cancel a running WebGAL Job."""
        with self._transaction() as db:
            db.execute(
                "UPDATE nar_messages m JOIN nar_conversations c ON c.id=m.conversation_id "
                "SET m.public_metadata=JSON_SET(m.public_metadata,'$.rpg.state','CANCELLED') "
                "WHERE m.id=%s AND m.conversation_id=%s AND m.role='assistant' "
                "AND c.owner_id=%s "
                "AND JSON_UNQUOTE(JSON_EXTRACT(m.public_metadata,'$.card_type'))='rpg' "
                "AND JSON_UNQUOTE(JSON_EXTRACT(m.public_metadata,'$.rpg.state'))='PREPARED'",
                (message_id, cid, owner))
            return db.rowcount == 1

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
