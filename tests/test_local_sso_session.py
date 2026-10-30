from contextlib import contextmanager
import hashlib
import time

import jwt
import pytest
from fastapi import HTTPException, Request

from webgal_backend import auth, sso_session

SECRET = 'test-only-portal-signing-secret-that-is-not-a-production-key'


def token(**changes):
    return jwt.encode({'sub': 'teacher', 'jti': 'random-session-id', 'iat': int(time.time()) - 1,
                       'exp': int(time.time()) + 60, **changes}, SECRET, algorithm='HS256')


@pytest.fixture
def local(monkeypatch):
    monkeypatch.setenv('WEBGAL_AUTH_MODE', 'sso')
    monkeypatch.setenv('WEBGAL_SSO_VALIDATION', 'database')
    monkeypatch.setenv('WEBGAL_SSO_JWT_SECRET', SECRET)
    monkeypatch.setenv('WEBGAL_SSO_COOKIE_NAME', 'nos_session')
    rows = [{'id': 'teacher', 'email': 'a@example.test', 'nickname': 'A', 'avatar_url': None,
             'provider': 'email', 'blocked': 0}]
    calls = []

    class Cursor:
        def execute(self, sql, args): calls.append((sql, args))
        def fetchall(self): return rows

    @contextmanager
    def transaction(): yield Cursor()

    monkeypatch.setattr(sso_session, 'database_transaction', transaction)
    monkeypatch.setattr(auth, 'urlopen', lambda *a, **k: pytest.fail('Local authentication must not call the portal'))
    return rows, calls


def request(value):
    return Request({'type': 'http', 'headers': [(b'cookie', f'nos_session={value}'.encode())]})


def test_local_identity_uses_one_query_and_no_remote_identity_request(local, tmp_path):
    rows, calls = local
    current = request(token())
    assert auth.user_from_request(current, tmp_path)['providers'] == ['email']
    assert auth.identity_from_request(current, tmp_path)['user_id'] == 'teacher'
    assert len(calls) == 1
    assert calls[0][1] == (hashlib.sha256(b'random-session-id').hexdigest(), 'teacher')
    assert 's.expires_at>CURRENT_TIMESTAMP(3)' in calls[0][0]
    assert 'FOR UPDATE' not in calls[0][0]


@pytest.mark.parametrize('value', [token(exp=1), token(jti=''), token(sub=42), 'not-a-token',
                                  jwt.encode({'sub': 'teacher', 'jti': 'x', 'exp': int(time.time())+60}, 'wrong-signing-secret-at-least-32-characters', algorithm='HS256')])
def test_invalid_tokens_never_reach_database(local, value):
    with pytest.raises(HTTPException) as exc: sso_session.session_user(value)
    assert exc.value.status_code == 401
    assert local[1] == []


def test_each_business_request_observes_revocation_and_blocking(local, tmp_path):
    rows, calls = local
    value = token()
    auth.user_from_request(request(value), tmp_path)
    rows[0]['blocked'] = 1
    with pytest.raises(HTTPException) as exc: auth.user_from_request(request(value), tmp_path)
    assert exc.value.status_code == 403
    rows.clear()
    with pytest.raises(HTTPException) as exc: auth.user_from_request(request(value), tmp_path)
    assert exc.value.status_code == 401
    assert len(calls) == 3


def test_local_mode_requires_secret_and_does_not_silently_downgrade(monkeypatch):
    monkeypatch.setenv('WEBGAL_SSO_VALIDATION', 'database')
    monkeypatch.delenv('WEBGAL_SSO_JWT_SECRET', raising=False)
    monkeypatch.delenv('AUTH_SECRET', raising=False)
    with pytest.raises(HTTPException) as exc: sso_session.local_session_enabled()
    assert exc.value.status_code == 503
    monkeypatch.setenv('WEBGAL_SSO_VALIDATION', 'auto')
    assert not sso_session.local_session_enabled()
