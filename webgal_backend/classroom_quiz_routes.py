"""HTTP adapter for classroom quizzes; owner checks are supplied by the host app."""
from __future__ import annotations

import csv
import io
import math
import threading
import time
from collections import OrderedDict
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .classroom_quiz import ClassroomQuiz, owner_key
from .storage import read_json
from .validators import ValidationFailure


class AssignmentInput(BaseModel):
    class_id: str | None = Field(None, max_length=32)
    class_name: str = Field('', max_length=100)
    name: str = Field('', max_length=120)
    new_round: bool = False


class AssignmentUpdate(BaseModel):
    status: Literal['OPEN', 'CLOSED']
    name: str | None = Field(None, max_length=120)


class NameInput(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class Answer(BaseModel):
    question_id: str = Field(min_length=1, max_length=20)
    option_id: str = Field(pattern='^[A-D]$')


class SubmissionInput(BaseModel):
    answers: list[Answer] = Field(min_length=1, max_length=10)


class VoidInput(BaseModel):
    reason: str = Field(min_length=1, max_length=400)


class SessionLimiter:
    """Only an authenticated attempt spends its own quota; networks/classes never share one.

    This bounded, per-process guard handles accidental request loops, not ingress abuse.
    Anonymous share/join requests have no application-level IP or class quota.
    """
    READ_LIMIT = 120
    WRITE_LIMIT = 30
    WINDOW_SECONDS = 60
    MAX_ENTRIES = 10000

    def __init__(self, clock=time.monotonic):
        self.entries = OrderedDict()
        self.lock = threading.Lock()
        self.clock = clock

    def check(self, attempt_id: str, write=False):
        key = (attempt_id, write)
        current = self.clock()
        with self.lock:
            start, count = self.entries.pop(key, (current, 0))
            if current - start >= self.WINDOW_SECONDS:
                start, count = current, 0
            self.entries[key] = (start, count + 1)
            while len(self.entries) > self.MAX_ENTRIES:
                self.entries.popitem(last=False)
            if count >= (self.WRITE_LIMIT if write else self.READ_LIMIT):
                retry_after = max(1, math.ceil(self.WINDOW_SECONDS - (current - start)))
                raise HTTPException(429, '当前作答页面请求过于频繁，请稍后重试', headers={'Retry-After': str(retry_after)})


def create_router(*, service: ClassroomQuiz, owned_job, identity, job_dir, frontend_url, make_llm, blocked):
    def no_cache(response: Response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
    router = APIRouter(tags=['classroom-quiz'], dependencies=[Depends(no_cache)])
    limiter = SessionLimiter()

    def owner(request):
        return owner_key(identity(request))

    def manage(aid, request):
        key = owner(request)
        a = service.get(aid, key)
        owned_job(a['job_id'], request)
        return key

    def credential(request):
        value = request.headers.get('X-Quiz-Credential', '')
        if not 20 <= len(value) <= 100:
            raise HTTPException(401, '作答凭证无效，请联系老师')
        return value

    def public_access(aid):
        a = service.get(aid)
        if blocked('JOB', a['job_id']):
            raise HTTPException(403, '该作品已下架')

    def attempt_access(tid, request, write=False):
        token = credential(request)
        result = service.attempt(tid, token)
        # Authenticate first: a guessed attempt id cannot consume another student's quota.
        limiter.check(result['id'], write)
        public_access(result['assignment_id'])
        return token, result

    def link_response(result):
        return {**result, 'url': f"{frontend_url.rstrip('/')}/practice/s/{result['token']}/"}

    @router.get('/quiz/classes')
    def classes(request: Request):
        return {'classes': service.classes(owner(request))}

    @router.get('/jobs/{job_id}/quiz/assignments')
    def assignments(job_id: str, request: Request):
        owned_job(job_id, request)
        return {'assignments': service.list(owner(request), job_id)}

    @router.post('/jobs/{job_id}/quiz/assignments', status_code=201)
    def create(job_id: str, payload: AssignmentInput, request: Request):
        owned_job(job_id, request)
        path = job_dir(job_id) / 'state/quiz_plan.json'
        if not path.exists():
            raise HTTPException(409, '请先生成习题')
        try:
            result = service.create(owner(request), job_id, read_json(path), payload.class_id, payload.class_name, payload.name,
                                    verify_job=lambda: owned_job(job_id, request), new_round=payload.new_round)
        except ValidationFailure as exc:
            raise HTTPException(422, exc.errors) from exc
        return link_response(result)

    @router.get('/quiz/assignments/{aid}')
    def get_assignment(aid: str, request: Request):
        return service.get(aid, manage(aid, request))

    @router.patch('/quiz/assignments/{aid}')
    def update(aid: str, payload: AssignmentUpdate, request: Request):
        service.update(aid, manage(aid, request), payload.status, payload.name)
        return {'saved': True}

    @router.get('/quiz/assignments/{aid}/share-links')
    def links(aid: str, request: Request):
        return {'links': service.links(aid, manage(aid, request))}

    @router.post('/quiz/assignments/{aid}/share-links')
    def share(aid: str, request: Request):
        return link_response(service.new_link(aid, manage(aid, request)))

    @router.delete('/quiz/assignments/{aid}/share-links/{lid}')
    def revoke(aid: str, lid: str, request: Request):
        service.revoke(aid, lid, manage(aid, request))
        return {'saved': True}

    @router.get('/quiz/assignments/{aid}/qr/{token}')
    def qr(aid: str, token: str, request: Request):
        manage(aid, request)
        if len(token) > 100:
            raise HTTPException(404, '分享链接不存在')
        # Verify the token really belongs to this exercise before rendering it.
        with service.transaction() as c:
            if service._link(c, token) != aid:
                raise HTTPException(404, '分享链接不存在')
        import qrcode
        import qrcode.image.svg
        image = qrcode.make(f"{frontend_url.rstrip('/')}/practice/s/{token}/", image_factory=qrcode.image.svg.SvgPathImage, border=4)
        return Response(image.to_string(), media_type='image/svg+xml', headers={'Cache-Control': 'no-store'})

    @router.get('/public/quiz/{token}')
    def info(token: str, request: Request):
        if len(token) > 100:
            raise HTTPException(404, '分享链接不存在')
        with service.transaction() as c:
            aid = service._link(c, token)
        public_access(aid)
        return service.public_info(token)

    @router.post('/public/quiz/{token}/join')
    def join(token: str, payload: NameInput, request: Request):
        with service.transaction() as c:
            aid = service._link(c, token)
        public_access(aid)
        return service.join(token, payload.name)

    @router.get('/public/quiz/attempts/{tid}')
    def attempt(tid: str, request: Request):
        return attempt_access(tid, request)[1]

    @router.patch('/public/quiz/attempts/{tid}/identity')
    def rename_student(tid: str, payload: NameInput, request: Request):
        token, _ = attempt_access(tid, request, True)
        service.mutate_attempt(tid, credential=token, name=payload.name)
        return service.attempt(tid, token)

    @router.post('/public/quiz/attempts/{tid}/submit')
    def submit(tid: str, payload: SubmissionInput, request: Request):
        token, _ = attempt_access(tid, request, True)
        service.mutate_attempt(tid, credential=token, answers=[answer.model_dump() for answer in payload.answers])
        return service.attempt(tid, token)

    @router.get('/quiz/assignments/{aid}/submissions')
    def submissions(aid: str, request: Request):
        return {'submissions': service.submissions(aid, manage(aid, request))}

    def manage_submission(tid, request):
        # Do not expose existence/identity of a submission to other teachers.
        key = owner(request)
        result = service.attempt(tid, owner=key)
        manage(result['assignment_id'], request)
        return key, result

    @router.get('/quiz/submissions/{tid}')
    def submission(tid: str, request: Request):
        return manage_submission(tid, request)[1]

    @router.patch('/quiz/submissions/{tid}/identity')
    def rename_teacher(tid: str, payload: NameInput, request: Request):
        key, _ = manage_submission(tid, request)
        service.mutate_attempt(tid, owner=key, name=payload.name)
        return service.attempt(tid, owner=key)

    @router.post('/quiz/submissions/{tid}/void')
    def void(tid: str, payload: VoidInput, request: Request):
        key, _ = manage_submission(tid, request)
        service.mutate_attempt(tid, owner=key, void_reason=payload.reason)
        return {'saved': True}

    @router.get('/quiz/assignments/{aid}/statistics')
    def stats(aid: str, request: Request):
        return service.stats(aid, manage(aid, request))

    def analyze(rid, job_id):
        # Construct the client inside the task so missing credentials also become a failed task.
        class LazyClient:
            client = None
            def call_text(self, *args):
                if self.client is None:
                    self.client = make_llm(job_id)
                return self.client.call_text(*args)
            def parse_json_text(self, *args):
                return self.client.parse_json_text(*args)
        service.run_analysis(rid, LazyClient())

    @router.post('/quiz/assignments/{aid}/analyses')
    def analysis(aid: str, request: Request, background_tasks: BackgroundTasks):
        key = manage(aid, request)
        rid, created = service.create_analysis(aid, key)
        if created:
            background_tasks.add_task(analyze, rid, service.get(aid, key)['job_id'])
        return {'id': rid, 'created': created}

    @router.get('/quiz/assignments/{aid}/analyses/latest')
    def latest(aid: str, request: Request):
        return {'analysis': service.latest_analysis(aid, manage(aid, request))}

    def safe_csv(value):
        text = str(value or '')
        return "'" + text if text.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else text

    @router.get('/quiz/assignments/{aid}/export')
    def export(aid: str, request: Request):
        key = manage(aid, request)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['姓名', '提交时间', '题目', '学生选项', '正确选项', '是否正确'])
        # A transaction snapshot keeps a concurrent void/rename from creating a mixed export.
        with service.transaction() as c:
            a = service._assignment(c, aid, key, True)
            snapshot = service._snapshot(c, a)
            c.execute("SELECT display_name,submitted_at,answers FROM quiz_attempts WHERE assignment_id=%s AND status='SUBMITTED' ORDER BY submitted_at", (aid,))
            import json
            for row in c.fetchall():
                answers = json.loads(row['answers'])
                for q in snapshot['quiz']['questions']:
                    answer = answers[q['id']]
                    writer.writerow([safe_csv(row['display_name']), row['submitted_at'], safe_csv(q['prompt']), answer['selected_option_id'], q['correct_option_ids'][0], '正确' if answer['is_correct'] else '错误'])
        return Response('\ufeff' + output.getvalue(), media_type='text/csv; charset=utf-8', headers={'Content-Disposition': 'attachment; filename="quiz-submissions.csv"', 'Cache-Control': 'no-store'})

    return router
