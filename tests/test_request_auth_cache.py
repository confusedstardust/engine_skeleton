import io
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from urllib.error import HTTPError

import pytest
from fastapi import HTTPException, Request

from webgal_backend import auth, platform_admin


def request(scope=None):
    return Request(scope if scope is not None else {'type': 'http', 'headers': [(b'cookie', b'nos_session=session-token')]})


@pytest.fixture
def sso(monkeypatch):
    monkeypatch.setenv('WEBGAL_AUTH_MODE', 'sso')
    monkeypatch.setenv('WEBGAL_SSO_USERINFO_URL', 'https://account.test/me')
    monkeypatch.setenv('WEBGAL_SSO_COOKIE_NAME', 'nos_session')
    calls = []
    blocked = []

    def userinfo(*args, **kwargs):
        calls.append(1)
        return io.BytesIO(json.dumps({'id': 'teacher', 'providers': ['email']}).encode())

    monkeypatch.setattr(auth, 'urlopen', userinfo)
    monkeypatch.setattr(platform_admin, 'blocked', lambda *args: blocked.append(args) or False)
    return calls, blocked


def test_nested_identity_checks_share_one_remote_lookup(sso, tmp_path):
    calls, blocked = sso
    original = request()
    assert auth.identity_from_request(original, tmp_path)['user_id'] == 'teacher'
    assert auth.user_from_request(original, tmp_path)['id'] == 'teacher'
    assert auth.identity_from_request(request(original.scope), tmp_path)['user_id'] == 'teacher'
    assert len(calls) == len(blocked) == 1
    auth.identity_from_request(request(), tmp_path)
    assert len(calls) == len(blocked) == 2


def test_cached_identity_cannot_be_modified_by_callers(sso, tmp_path):
    current = request()
    principal = auth.principal_from_request(current, tmp_path)
    principal['identity']['user_id'] = 'someone-else'
    principal['user']['providers'].append('changed')
    assert auth.identity_from_request(current, tmp_path)['user_id'] == 'teacher'
    assert auth.user_from_request(current, tmp_path)['providers'] == ['email']


def test_parallel_checks_in_one_request_share_inflight_lookup(sso, monkeypatch, tmp_path):
    calls = []
    entered, release = Event(), Event()
    lock = Lock()

    def userinfo(*args, **kwargs):
        with lock:
            calls.append(1)
        entered.set()
        assert release.wait(5)
        return io.BytesIO(b'{"id":"teacher"}')

    monkeypatch.setattr(auth, 'urlopen', userinfo)
    current = request()
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(auth.identity_from_request, current, tmp_path)
        assert entered.wait(5)
        rest = [pool.submit(auth.user_from_request, request(current.scope), tmp_path) for _ in range(2)]
        release.set()
        assert first.result()['user_id'] == 'teacher'
        assert all(f.result()['id'] == 'teacher' for f in rest)
    assert len(calls) == 1


def test_next_request_rechecks_expired_session_and_blocked_user(sso, monkeypatch, tmp_path):
    auth.identity_from_request(request(), tmp_path)
    monkeypatch.setattr(platform_admin, 'blocked', lambda *args: True)
    with pytest.raises(HTTPException) as error:
        auth.identity_from_request(request(), tmp_path)
    assert error.value.status_code == 403
    monkeypatch.setattr(platform_admin, 'blocked', lambda *args: False)

    def expired(*args, **kwargs):
        raise HTTPError('https://account.test/me', 401, 'expired', {}, None)

    monkeypatch.setattr(auth, 'urlopen', expired)
    with pytest.raises(HTTPException) as error:
        auth.identity_from_request(request(), tmp_path)
    assert error.value.status_code == 401


def test_invite_cache_does_not_cross_workspaces(monkeypatch, tmp_path):
    monkeypatch.setenv('WEBGAL_AUTH_MODE', 'invite')
    monkeypatch.delenv('WEBGAL_INVITE_CODES', raising=False)
    monkeypatch.setenv('WEBGAL_INVITE_CODES_FILE', 'invites.txt')
    first, second = tmp_path / 'first', tmp_path / 'second'
    first.mkdir()
    second.mkdir()
    (first / 'invites.txt').write_text('allowed')
    (second / 'invites.txt').write_text('other')
    current = Request({'type': 'http', 'headers': [(b'x-webgal-invite-code', b'allowed')]})
    assert auth.identity_from_request(current, first)['type'] == 'invite'
    with pytest.raises(HTTPException) as error:
        auth.identity_from_request(current, second)
    assert error.value.status_code == 403
