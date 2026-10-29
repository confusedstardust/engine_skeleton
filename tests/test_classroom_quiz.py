"""Isolated transactional service/API tests. SQLite adapter does not prove MySQL lock behavior."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from pathlib import Path
import json
import re
import sqlite3

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from webgal_backend.classroom_quiz import ClassroomQuiz, digest, generate_analysis, now
from webgal_backend.classroom_quiz_routes import SessionLimiter, create_router


def quiz():
    return {'title': '课后习题', 'introduction': '检查理解', 'questions': [
        {'id': f'q{i}', 'type': 'single_choice' if i % 2 else 'judgement', 'prompt': f'题目{i}',
         'options': [{'id': key, 'text': ('正确' if key == 'A' else '错误') if not i % 2 else key} for key in ('ABCD' if i % 2 else 'AB')],
         'correct_option_ids': ['A'], 'explanation': '来自材料', 'knowledge_point': '概念', 'difficulty': '基础', 'teaching_tip': '说明依据'}
        for i in range(1, 5)]}


class Cursor:
    def __init__(self, connection):
        self.cursor = connection.cursor()

    def execute(self, sql, params=()):
        sql = sql.replace('%s', '?').replace(' FOR UPDATE', '').replace('INSERT IGNORE', 'INSERT OR IGNORE')
        self.cursor.execute(sql, params)
        return self

    @property
    def rowcount(self):
        return self.cursor.rowcount

    def fetchone(self):
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def fetchall(self):
        return [dict(row) for row in self.cursor.fetchall()]


@pytest.fixture
def service(tmp_path):
    path = tmp_path / 'test.db'
    # Derive SQLite table definitions from production DDL; preserve unique and foreign keys.
    sql = (Path(__file__).parents[1] / 'webgal_backend/migrations/001_classroom_quiz.sql').read_text()
    sql = re.sub(r'\) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin', ')', sql)
    sql = re.sub(r'UNIQUE KEY \w+\s*\(', 'UNIQUE (', sql)
    sql = re.sub(r',\s*INDEX \w+\s*\([^)]*\)', '', sql)
    connection = sqlite3.connect(path)
    connection.executescript(sql)
    connection.close()

    @contextmanager
    def transaction():
        conn = sqlite3.connect(path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('BEGIN IMMEDIATE')
        try:
            yield Cursor(conn)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    return ClassroomQuiz(transaction, job_guard_factory=lambda _: nullcontext())


@pytest.fixture
def exercise(service):
    return service.create('owner', 'a' * 32, quiz(), None, '三年二班', '')


def answers(option='A'):
    return [{'question_id': f'q{i}', 'option_id': option} for i in range(1, 5)]


def submit(service, session, selected=None):
    service.mutate_attempt(session['id'], credential=session['credential'], answers=selected or answers())


def test_student_redaction_and_submission(service, exercise):
    student = service.join(exercise['token'], ' 小明 ')
    draft = service.attempt(student['id'], student['credential'])
    assert draft['display_name'] == '小明'
    for question in draft['quiz']['questions']:
        assert set(question) == {'id', 'type', 'prompt', 'options'}
    assert draft['answers'] == {}
    submit(service, student)
    result = service.attempt(student['id'], student['credential'])
    assert result['status'] == 'SUBMITTED'
    assert result['answers']['q1']['is_correct']
    assert result['quiz']['questions'][0]['correct_option_ids'] == ['A']
    assert not any(key in result for key in ('score', 'student_number', 'rank'))


def test_twenty_question_assignment_can_be_submitted(service):
    from copy import deepcopy
    from webgal_backend.classroom_quiz_routes import SubmissionInput
    plan = quiz()
    plan['questions'].extend([{**deepcopy(plan['questions'][0]), 'id': f'q{i}'} for i in range(5, 21)])
    exercise = service.create('owner', 'a' * 32, plan, None, '班级', '')
    session = service.join(exercise['token'], '学生')
    payload = SubmissionInput(answers=[{'question_id': q['id'], 'option_id': 'A'} for q in plan['questions']])
    service.mutate_attempt(session['id'], credential=session['credential'], answers=[a.model_dump() for a in payload.answers])
    assert len(service.attempt(session['id'], session['credential'])['answers']) == 20


def test_latest_analysis_does_not_recompute_class_statistics(service, exercise, monkeypatch):
    student = service.join(exercise['token'], '小明')
    submit(service, student)
    service.create_analysis(exercise['assignment_id'], 'owner')
    monkeypatch.setattr(service, '_snapshot', lambda *args: pytest.fail('latest must not recompute statistics'))
    report = service.latest_analysis(exercise['assignment_id'], 'owner')
    assert report['status'] == 'QUEUED'
    assert report['added_count'] == report['voided_count'] == 0


def test_teacher_view_authenticates_once_and_still_rejects_other_owner(service, monkeypatch, tmp_path):
    import io
    from webgal_backend import auth, platform_admin
    from webgal_backend.classroom_quiz import owner_key

    monkeypatch.setenv('WEBGAL_AUTH_MODE', 'sso')
    monkeypatch.setenv('WEBGAL_SSO_USERINFO_URL', 'https://account.test/me')
    monkeypatch.setenv('WEBGAL_SSO_COOKIE_NAME', 'nos_session')
    user_id, lookups, ownership_checks = 'teacher', [], []

    def userinfo(*args, **kwargs):
        lookups.append(user_id)
        return io.BytesIO(json.dumps({'id': user_id}).encode())

    monkeypatch.setattr(auth, 'urlopen', userinfo)
    monkeypatch.setattr(platform_admin, 'blocked', lambda *args: False)
    teacher = {'type': 'sso', 'user_id': 'teacher'}
    exercise = service.create(owner_key(teacher), 'a' * 32, quiz(), None, '班级', '')
    student = service.join(exercise['token'], '小明')
    submit(service, student)

    def owned_job(job_id, request):
        ownership_checks.append(job_id)
        if not auth.job_belongs_to_identity({'identity': teacher}, auth.identity_from_request(request, tmp_path)):
            raise HTTPException(404, 'not found')

    app = FastAPI()
    app.include_router(create_router(service=service, owned_job=owned_job,
        identity=lambda request: auth.identity_from_request(request, tmp_path),
        job_dir=lambda _: tmp_path, frontend_url='https://example.test',
        make_llm=lambda _: None, blocked=lambda *args: False))
    client = TestClient(app)
    client.cookies.set('nos_session', 'session-token')
    response = client.get(f"/quiz/submissions/{student['id']}")
    assert response.status_code == 200
    assert response.json()['display_name'] == '小明'
    assert lookups == ['teacher']
    assert ownership_checks == ['a' * 32]
    user_id = 'other-teacher'
    assert client.get(f"/quiz/submissions/{student['id']}").status_code == 404
    assert lookups == ['teacher', 'other-teacher']


@pytest.mark.parametrize('invalid', [answers()[:-1], answers() + answers()[:1], [*answers()[:3], answers()[0]], [dict(x, option_id='Z') for x in answers()]])
def test_incomplete_duplicate_extra_invalid_options(service, exercise, invalid):
    session = service.join(exercise['token'], '小明')
    with pytest.raises(HTTPException) as error:
        submit(service, session, invalid)
    assert error.value.status_code == 422
    assert service.submissions(exercise['assignment_id'], 'owner') == []


def test_idempotency_closure_and_versions(service, exercise):
    session = service.join(exercise['token'], '小明')
    submit(service, session)
    aid = exercise['assignment_id']
    service.update(aid, 'owner', 'CLOSED')
    submit(service, session, answers('B'))  # A lost response must never change the stored answers.
    assert service.attempt(session['id'], session['credential'])['answers']['q1']['selected_option_id'] == 'A'
    assert len(service.submissions(aid, 'owner')) == 1
    changed = quiz()
    changed['questions'][0]['prompt'] = '新题目'
    service.create('owner', 'a' * 32, changed, None, '另一个班', '')
    assert service.attempt(session['id'], session['credential'])['quiz']['questions'][0]['prompt'] == '题目1'
    assert service.get(aid)['data_revision'] == 1


def test_unique_names_concurrent_and_database_constraint(service, exercise):
    sessions = [service.join(exercise['token'], '同名') for _ in range(4)]
    def send(s):
        try:
            submit(service, s)
            return 200
        except HTTPException as exc:
            return exc.status_code
    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(send, sessions))
    assert statuses.count(200) == 1 and statuses.count(409) == 3
    with service.transaction() as c:
        with pytest.raises(sqlite3.IntegrityError):
            c.execute("UPDATE quiz_attempts SET submitted_name='同名',status='SUBMITTED' WHERE id=%s", (sessions[statuses.index(409)]['id'],))


def test_authorization_and_void_releases_name(service, exercise):
    session = service.join(exercise['token'], '小明')
    with pytest.raises(HTTPException):
        service.attempt(session['id'], 'wrong')
    with pytest.raises(HTTPException):
        service.attempt(session['id'], owner='different-owner')
    submit(service, session)
    with pytest.raises(HTTPException):
        service.join(exercise['token'], '小明')
    service.mutate_attempt(session['id'], owner='owner', void_reason='误填')
    with pytest.raises(HTTPException) as error:
        service.attempt(session['id'], session['credential'])
    assert error.value.status_code == 410
    assert service.stats(exercise['assignment_id'], 'owner')['submitted_count'] == 0
    replacement = service.join(exercise['token'], '小明')
    submit(service, replacement)
    assert len(service.submissions(exercise['assignment_id'], 'owner')) == 1


def test_closed_and_revoked_link_existing_session(service, exercise):
    session = service.join(exercise['token'], '小明')
    aid = exercise['assignment_id']
    service.revoke(aid, exercise['link_id'], 'owner')
    with pytest.raises(HTTPException):
        service.public_info(exercise['token'])
    service.update(aid, 'owner', 'CLOSED')
    with pytest.raises(HTTPException):
        submit(service, session)
    service.update(aid, 'owner', 'OPEN')
    submit(service, session)
    assert service.attempt(session['id'], session['credential'])['status'] == 'SUBMITTED'


def test_sharing_again_reuses_class_and_exercise(service, exercise):
    session = service.join(exercise['token'], '小明')
    submit(service, session)
    repeated = service.create('owner', 'a' * 32, quiz(), None, '三年二班', '')
    assert repeated['reused'] and repeated['assignment_id'] == exercise['assignment_id']
    assert repeated['token'] == exercise['token']
    assert len(service.classes('owner')) == 1
    assert len(service.list('owner', 'a' * 32)) == 1
    assert len(service.submissions(repeated['assignment_id'], 'owner')) == 1
    reopened = service.new_link(exercise['assignment_id'], 'owner')
    assert reopened['token'] == exercise['token']
    assert len(service.links(exercise['assignment_id'], 'owner')) == 1
    service.revoke(exercise['assignment_id'], exercise['link_id'], 'owner')
    replacement = service.new_link(exercise['assignment_id'], 'owner')
    assert replacement['token'] != exercise['token']
    assert service.new_link(exercise['assignment_id'], 'owner')['token'] == replacement['token']


def test_name_correction_expiry_and_audit(service, exercise):
    session = service.join(exercise['token'], '错名')
    service.mutate_attempt(session['id'], credential=session['credential'], name='正名')
    submit(service, session)
    service.mutate_attempt(session['id'], owner='owner', name='更正名')
    assert service.submissions(exercise['assignment_id'], 'owner')[0]['display_name'] == '更正名'
    with service.transaction() as c:
        c.execute("UPDATE quiz_attempts SET expires_at='2000' WHERE id=%s", (session['id'],))
    with pytest.raises(HTTPException):
        service.attempt(session['id'], session['credential'])


def valid_report():
    return {'overview': '本次练习显示概念理解有待巩固。', 'items': [
        {'kind': kind, 'text': '可能混淆概念，建议结合材料追问依据。', 'question_ids': ['q1']}
        for kind in ('共性误区', '优先讲评', '知识点回顾', '教学建议', '题目质量')]}


class FakeLLM:
    def __init__(self, report=None):
        self.report = report or valid_report()
        self.prompts = []
    def call_text(self, name, system, prompt):
        self.prompts.append(prompt)
        return json.dumps(self.report, ensure_ascii=False)
    def parse_json_text(self, text, name):
        return json.loads(text)


def test_analysis_statistics_snapshots_privacy_and_changes(service, exercise):
    aid = exercise['assignment_id']
    assert service.stats(aid, 'owner')['questions'][0]['correct_rate'] is None
    with pytest.raises(HTTPException):
        service.create_analysis(aid, 'owner')
    first = service.join(exercise['token'], '秘密姓名')
    submit(service, first)
    rid, created = service.create_analysis(aid, 'owner')
    assert created
    assert service.create_analysis(aid, 'owner') == (rid, False)
    llm = FakeLLM()
    service.run_analysis(rid, llm)
    assert '秘密姓名' not in ''.join(llm.prompts)
    report = service.latest_analysis(aid, 'owner')
    assert report['status'] == 'READY' and not report['stale']
    second = service.join(exercise['token'], '另一个学生')
    submit(service, second, answers('B'))
    service.mutate_attempt(first['id'], owner='owner', void_reason='误填')
    report = service.latest_analysis(aid, 'owner')
    assert report['stale'] and report['added_count'] == 1 and report['voided_count'] == 1
    assert report['snapshot']['statistics']['questions'][0]['correct_rate'] == 1
    assert service.stats(aid, 'owner')['questions'][0]['correct_rate'] == 0
    new_id, _ = service.create_analysis(aid, 'owner')
    latest = service.latest_analysis(aid, 'owner')
    assert not latest['stale']
    assert latest['previous']['result'] and latest['previous']['stale']
    assert latest['previous']['added_count'] == 1 and latest['previous']['voided_count'] == 1
    with service.transaction() as c:
        c.execute("UPDATE quiz_analysis_runs SET lease_until='2000' WHERE id=%s", (new_id,))
    assert service.latest_analysis(aid, 'owner')['status'] == 'FAILED'
    service.run_analysis(new_id, llm)
    assert service.latest_analysis(aid, 'owner')['status'] == 'FAILED'
    assert service.create_analysis(aid, 'owner')[1]


def test_report_rejects_hallucinated_references_and_numbers(service, exercise):
    student = service.join(exercise['token'], '小明')
    submit(service, student)
    rid, _ = service.create_analysis(exercise['assignment_id'], 'owner')
    report = valid_report()
    report['items'][0]['question_ids'] = ['q99']
    service.run_analysis(rid, FakeLLM(report))
    assert service.latest_analysis(exercise['assignment_id'], 'owner')['status'] == 'FAILED'
    report = valid_report()
    report['overview'] = '正确率 99%'
    with pytest.raises(ValueError):
        generate_analysis({'quiz': quiz(), 'statistics': {}}, FakeLLM(report))


def test_http_flow_owner_guards_qr_and_export(service, tmp_path):
    from webgal_backend.classroom_quiz import owner_key
    source = tmp_path / 'state'
    source.mkdir()
    (source / 'quiz_plan.json').write_text(json.dumps(quiz()), encoding='utf-8')
    def identity(request):
        if request.headers.get('teacher') != 'yes':
            raise HTTPException(401, '请登录')
        return {'type': 'sso', 'user_id': 'teacher'}
    def owned(job, request):
        identity(request)
        if job != 'a' * 32:
            raise HTTPException(404, '不存在')
    app = FastAPI()
    app.include_router(create_router(service=service, owned_job=owned, identity=identity, job_dir=lambda job: tmp_path,
        frontend_url='https://example.com/narrativeos', make_llm=lambda job: FakeLLM(), blocked=lambda kind, job: False))
    client = TestClient(app)
    teacher = {'teacher': 'yes'}
    assert client.get('/quiz/classes').status_code == 401
    response = client.post(f"/jobs/{'a' * 32}/quiz/assignments", headers=teacher, json={'class_name': '班级'})
    assert response.status_code == 201, response.text
    link = response.json()
    aid = link['assignment_id']
    assert link['url'].startswith('https://example.com/narrativeos/practice/s/')
    assert client.get(f"/quiz/assignments/{aid}/qr/{link['token']}", headers=teacher).headers['content-type'].startswith('image/svg+xml')
    assert 'quiz' not in client.get(f"/public/quiz/{link['token']}").json()
    session = client.post(f"/public/quiz/{link['token']}/join", json={'name': '=学生'}).json()
    tid = session['id']; credential = {'X-Quiz-Credential': session['credential']}
    assert client.get(f'/public/quiz/attempts/{tid}').status_code == 401
    assert client.get(f'/quiz/submissions/{tid}').status_code == 401
    submitted = client.post(f'/public/quiz/attempts/{tid}/submit', headers=credential, json={'answers': answers()})
    assert submitted.status_code == 200
    assert client.post(f'/public/quiz/attempts/{tid}/submit', headers=credential, json={'answers': answers()}).status_code == 200
    assert len(client.get(f'/quiz/assignments/{aid}/submissions', headers=teacher).json()['submissions']) == 1
    exported = client.get(f'/quiz/assignments/{aid}/export', headers=teacher)
    assert "'=学生" in exported.text
    assert '得分' not in exported.text
    assert client.post(f'/quiz/assignments/{aid}/analyses', headers=teacher).status_code == 200
    assert client.get(f'/quiz/assignments/{aid}/analyses/latest', headers=teacher).json()['analysis']['status'] == 'READY'


def test_session_protection_expires_and_keeps_students_and_operations_separate():
    clock = [100.0]
    limiter = SessionLimiter(clock=lambda: clock[0])
    for _ in range(limiter.READ_LIMIT):
        limiter.check('student-a')
    with pytest.raises(HTTPException) as error:
        limiter.check('student-a')
    assert error.value.status_code == 429
    assert error.value.headers['Retry-After'] == '60'
    limiter.check('student-b')
    limiter.check('student-a', write=True)
    clock[0] += 60
    limiter.check('student-a')


@pytest.fixture
def session_protection_client():
    """Exercise HTTP quota wiring without involving a database or real network."""
    from types import SimpleNamespace

    @contextmanager
    def transaction():
        yield None

    valid = 'valid-student-session-credential'
    def attempt(tid, credential):
        if credential != valid:
            raise HTTPException(404, '凭证无效')
        return {'id': tid, 'assignment_id': tid.split(':')[0]}

    service = SimpleNamespace(
        transaction=transaction,
        _link=lambda _, token: token,
        get=lambda aid: {'job_id': aid},
        public_info=lambda token: {'name': token, 'status': 'OPEN'},
        join=lambda token, name: {'id': f'{token}:{name}', 'credential': valid},
        attempt=attempt,
        mutate_attempt=lambda *args, **kwargs: None,
    )
    app = FastAPI()
    app.include_router(create_router(
        service=service, owned_job=lambda *args: None, identity=lambda request: {},
        job_dir=lambda job: None, frontend_url='https://example.com',
        make_llm=lambda job: None, blocked=lambda *args: False,
    ))
    return TestClient(app, client=('shared-school-proxy', 50000)), valid


def test_shared_school_proxy_has_no_scan_or_join_quota(session_protection_client):
    client, _ = session_protection_client
    # Exceed the old global IP thresholds. All requests have the very same proxy address,
    # and alternate between two classes; neither class consumes the other's capacity.
    for i in range(1201):
        response = client.get(f'/public/quiz/class-{i % 2}')
        assert response.status_code == 200
    for i in range(301):
        response = client.post(f'/public/quiz/class-{i % 2}/join', json={'name': f'学生{i}'})
        assert response.status_code == 200


def test_authenticated_attempts_cannot_spend_other_students_quota(session_protection_client):
    client, credential = session_protection_client
    headers = {'X-Quiz-Credential': credential}
    path = '/public/quiz/attempts/class-a:student-a'
    # Forging the id with a wrong credential must not consume a genuine session's allowance.
    for _ in range(31):
        assert client.patch(path + '/identity', headers={'X-Quiz-Credential': 'incorrect-credential-long-enough'}, json={'name': '小明'}).status_code == 404
    for _ in range(30):
        assert client.patch(path + '/identity', headers=headers, json={'name': '小明'}).status_code == 200
    throttled = client.patch(path + '/identity', headers=headers, json={'name': '小明'})
    assert throttled.status_code == 429 and int(throttled.headers['Retry-After']) > 0
    # Same proxy and same class, different student; then a student in another class.
    for tid in ('class-a:student-b', 'class-b:student-c'):
        assert client.patch(f'/public/quiz/attempts/{tid}/identity', headers=headers, json={'name': '小红'}).status_code == 200
    # Exhausted writes do not stop normal polling or new students scanning/joining.
    assert client.get(path, headers=headers).status_code == 200
    assert client.get('/public/quiz/class-a').status_code == 200
    assert client.post('/public/quiz/class-a/join', json={'name': '新同学'}).status_code == 200
