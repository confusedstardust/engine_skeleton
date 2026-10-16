"""Public notices and moderated Q&A. Private questions stay visible to their author."""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, field_validator

from .auth import user_from_request
from .database import database_transaction
from .config import settings
from .platform_admin import require_action_header, require_admin

router = APIRouter(tags=["community"])


class Question(BaseModel):
    question: str = Field(min_length=5, max_length=2000)
    kind: Literal["QUESTION", "SUGGESTION"] = "QUESTION"

    @field_validator("question", mode="before")
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value


class Answer(BaseModel):
    answer: str = Field(max_length=4000)
    published: bool = False


class Announcement(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=2000)
    published: bool = True

    @field_validator("title", "content", mode="before")
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value


def account(request: Request):
    user = user_from_request(request, settings.workspace_root)
    if user.get("auth_type") != "sso":
        raise HTTPException(401, "请登录账号后提问")
    return user


@router.get("/community")
def public_board(offset: int = Query(0, ge=0)):
    with database_transaction() as cursor:
        cursor.execute("SELECT id,title,content,created_at FROM community_announcements WHERE published=1 ORDER BY created_at DESC,id DESC LIMIT 3")
        notices = cursor.fetchall()
        cursor.execute("SELECT id,question,answer,created_at FROM community_questions WHERE published=1 AND kind='QUESTION' ORDER BY created_at DESC,id DESC LIMIT 7 OFFSET %s", (offset,))
        questions = cursor.fetchall()
    return {"announcements": notices, "questions": questions[:6], "has_more": len(questions) > 6}


@router.get("/community/mine")
def my_questions(request: Request, offset: int = Query(0, ge=0), kind: Literal["QUESTION", "SUGGESTION"] = "QUESTION"):
    user = account(request)
    with database_transaction() as cursor:
        cursor.execute("SELECT id,kind,question,answer,published,created_at FROM community_questions WHERE user_id=%s AND kind=%s ORDER BY created_at DESC,id DESC LIMIT 7 OFFSET %s", (user["id"], kind, offset))
        rows = cursor.fetchall()
    return {"questions": rows[:6], "has_more": len(rows) > 6}


@router.post("/community/questions", status_code=201)
def ask(payload: Question, request: Request, response: Response):
    if request.headers.get("x-forge-community-action") != "1":
        raise HTTPException(403, "无效提问请求")
    user = account(request)
    identifier = uuid.uuid4().hex
    with database_transaction() as cursor:
        # Serialize submissions for the same account across workers.
        cursor.execute("SELECT id FROM users WHERE id=%s FOR UPDATE", (user["id"],))
        if not cursor.fetchone():
            raise HTTPException(401, "账号不存在，请重新登录")
        cursor.execute("SELECT id FROM community_questions WHERE user_id=%s AND kind=%s AND question=%s AND created_at > DATE_SUB(UTC_TIMESTAMP(3), INTERVAL 1 MINUTE) LIMIT 1", (user["id"], payload.kind, payload.question))
        existing = cursor.fetchone()
        if existing:
            response.status_code = 200
            return {"id": existing["id"], "duplicate": True}
        cursor.execute("INSERT INTO community_questions (id,user_id,author_name,question,kind) VALUES (%s,%s,%s,%s,%s)", (identifier, user["id"], str(user.get("nickname") or "创作者")[:100], payload.question, payload.kind))
    return {"id": identifier}


@router.get("/admin/community")
def admin_board(request: Request, offset: int = Query(0, ge=0)):
    require_admin(request)
    with database_transaction() as cursor:
        cursor.execute("SELECT * FROM community_announcements ORDER BY created_at DESC,id DESC LIMIT 50")
        notices = cursor.fetchall()
        cursor.execute("SELECT * FROM community_questions ORDER BY (answer IS NULL) DESC,created_at DESC,id DESC LIMIT 21 OFFSET %s", (offset,))
        questions = cursor.fetchall()
    return {"announcements": notices, "questions": questions[:20], "has_more": len(questions) > 20}


@router.put("/admin/community/questions/{identifier}")
def reply(identifier: str, payload: Answer, request: Request):
    require_action_header(request)
    require_admin(request)
    answer = payload.answer.strip()
    if payload.published and not answer:
        raise HTTPException(422, "填写答复后才能公开问答")
    with database_transaction() as cursor:
        cursor.execute("SELECT id,kind FROM community_questions WHERE id=%s FOR UPDATE", (identifier,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "问题不存在")
        if payload.published and row["kind"] == "SUGGESTION":
            raise HTTPException(422, "建议仅对提交者和管理员可见")
        cursor.execute("UPDATE community_questions SET answer=%s,published=%s,answered_at=UTC_TIMESTAMP(3) WHERE id=%s", (answer or None, payload.published, identifier))
    return {"saved": True}


@router.post("/admin/community/announcements", status_code=201)
def create_notice(payload: Announcement, request: Request):
    require_action_header(request)
    require_admin(request)
    identifier = uuid.uuid4().hex
    with database_transaction() as cursor:
        cursor.execute("INSERT INTO community_announcements (id,title,content,published) VALUES (%s,%s,%s,%s)", (identifier, payload.title, payload.content, payload.published))
    return {"id": identifier}


@router.put("/admin/community/announcements/{identifier}")
def edit_notice(identifier: str, payload: Announcement, request: Request):
    require_action_header(request)
    require_admin(request)
    with database_transaction() as cursor:
        cursor.execute("SELECT id FROM community_announcements WHERE id=%s FOR UPDATE", (identifier,))
        if not cursor.fetchone():
            raise HTTPException(404, "公告不存在")
        cursor.execute("UPDATE community_announcements SET title=%s,content=%s,published=%s WHERE id=%s", (payload.title, payload.content, payload.published, identifier))
    return {"saved": True}
