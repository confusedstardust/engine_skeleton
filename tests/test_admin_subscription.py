from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import webgal_backend.platform_admin as admin


def test_subscription_admin_auth_required(monkeypatch):
    def deny(_):
        raise HTTPException(403, 'denied')
    monkeypatch.setattr(admin, 'require_admin', deny)
    app = FastAPI(); app.include_router(admin.router)
    client = TestClient(app)
    assert client.get('/admin/users/u/detail').status_code == 403
    assert client.patch('/admin/users/u/subscription', json={'plan':'Free','reason':'test','expected_revision':0}).status_code == 403


def test_subscription_mutation_rejects_missing_action_header_and_invalid_expiry(monkeypatch):
    monkeypatch.setattr(admin, 'require_admin', lambda _: {'id':'admin'})
    app = FastAPI(); app.include_router(admin.router)
    client = TestClient(app)
    payload = {'plan':'Creator','reason':'test','expected_revision':0}
    assert client.patch('/admin/users/u/subscription', json=payload).status_code == 403
    for value in [None, 'invalid', '2020-01-01T00:00:00Z', '2030-01-01T00:00:00']:
        assert client.patch('/admin/users/u/subscription', json={**payload,'expires_at':value}, headers={'x-forge-admin-action':'1'}).status_code == 422
    assert client.patch('/admin/users/u/subscription', json={**payload,'plan':'Free','reason':' '}, headers={'x-forge-admin-action':'1'}).status_code == 422
