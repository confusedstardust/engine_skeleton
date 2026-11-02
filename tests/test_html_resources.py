import io
import zipfile
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from webgal_backend import html_resources as resources


def package(files):
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return data.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(resources, 'settings', SimpleNamespace(jobs_dir=tmp_path))
    monkeypatch.setattr(resources, 'require_admin', lambda request: {'id': 'admin-user'})
    monkeypatch.setattr(resources, 'ecosystem_change', lambda actor, identifier, owner, action, operation: operation())
    monkeypatch.setenv('WEBGAL_FRONTEND_URL', 'https://example.com/forge')
    monkeypatch.setattr(resources, 'publish_work', lambda payload: {'published': True, 'work': payload})
    monkeypatch.setattr(resources, 'unpublish_work', lambda *args: {'published': False})
    app = FastAPI()
    app.include_router(resources.router)
    return TestClient(app, headers={'X-Forge-Admin-Action': '1'})


def upload(client, **overrides):
    return client.post('/admin/html-resources', data={'title': '行星实验室', 'subject': '科学', 'curriculum': 'IB', 'stage': '小学', **overrides},
                       files={'file': ('lesson.zip', package({'lesson/index.html': '<script src="app.js"></script>', 'lesson/app.js': 'window.ready=true;'}), 'application/zip')})


def test_upload_publishes_existing_contract_and_serves_sandboxed_package(client):
    response = upload(client)
    assert response.status_code == 200
    result = response.json()
    identifier = result['id']
    assert result['payload']['ownerUserId'] == 'admin-user'
    assert result['payload']['tags'] == ['IB', '小学', 'HTML互动资源']
    assert result['payload']['playUrl'] == f'https://example.com/forge/resources-play/{identifier}/'
    assert result['entry'] == 'lesson/index.html'
    player = client.get(f'/resources-play/{identifier}/')
    assert 'sandbox="allow-scripts allow-downloads"' in player.text
    assert 'allow-same-origin' not in player.text
    script = client.get(f'/resources-play/{identifier}/files/lesson/app.js')
    assert script.status_code == 200 and script.text == 'window.ready=true;'
    assert 'sandbox allow-scripts' in script.headers['content-security-policy']
    assert script.headers['access-control-allow-origin'] == '*'
    assert client.get('/admin/html-resources').json()['items'][0]['state'] == 'published'
    assert client.delete(f'/admin/html-resources/{identifier}/publication').status_code == 200
    assert client.get(f'/resources-play/{identifier}/').status_code == 404
    assert client.get(f'/resources-play/{identifier}/files/lesson/app.js').status_code == 404
    assert client.post(f'/admin/html-resources/{identifier}/publication').json()['published']


@pytest.mark.parametrize('subject', ['', '任意学科'])
def test_subject_required_and_controlled(client, subject):
    assert upload(client, subject=subject).status_code == 422
    assert not list(resources.resource_root().glob('*/metadata.json'))


def test_single_html_and_optional_classification(client):
    response = client.post('/admin/html-resources', data={'title': '课堂', 'subject': '数学'}, files={'file': ('lesson.html', '<h1>课堂</h1>', 'text/html')})
    assert response.status_code == 200
    assert response.json()['entry'] == 'index.html'
    assert response.json()['payload']['grade'] is None


def test_auth_and_csrf(client, monkeypatch):
    client.headers.pop('X-Forge-Admin-Action')
    assert upload(client).status_code == 403
    monkeypatch.setattr(resources, 'require_admin', lambda request: (_ for _ in ()).throw(HTTPException(403)))
    assert client.get('/admin/html-resources').status_code == 403
    assert client.get('/admin/html-resources/taxonomy').status_code == 403


@pytest.mark.parametrize('name', ['../escape.html', '/absolute.html', 'C:/drive.html', 'dir/.secret.html', 'server.php'])
def test_reject_unsafe_archive(client, name):
    response = client.post('/admin/html-resources', data={'title': '课堂', 'subject': '数学'}, files={'file': ('bad.zip', package({name: 'bad'}), 'application/zip')})
    assert response.status_code == 422
    assert not list(resources.resource_root().glob('*'))


def test_ambiguous_entry_and_explicit_selection(client):
    files = {'file': ('lesson.zip', package({'a.html': 'a', 'b.html': 'b'}), 'application/zip')}
    assert client.post('/admin/html-resources', data={'title': '课堂', 'subject': '数学'}, files=files).status_code == 422
    assert client.post('/admin/html-resources', data={'title': '课堂', 'subject': '数学', 'entry': 'b.html'}, files=files).json()['entry'] == 'b.html'


def test_publish_failure_keeps_same_resource_for_retry(client, monkeypatch):
    def fail(*args):
        raise HTTPException(503, 'service unavailable')
    monkeypatch.setattr(resources, 'ecosystem_change', fail)
    assert upload(client).status_code == 503
    saved = client.get('/admin/html-resources').json()['items'][0]
    assert saved['state'] == 'publishing'
    monkeypatch.setattr(resources, 'ecosystem_change', lambda actor, identifier, owner, action, operation: operation())
    assert client.post(f"/admin/html-resources/{saved['id']}/publication").status_code == 200
    assert len(client.get('/admin/html-resources').json()['items']) == 1


def test_corrupt_and_oversized_packages(client, monkeypatch):
    monkeypatch.setattr(resources, 'MAX_UPLOAD', 20)
    assert client.post('/admin/html-resources', data={'title': '课堂', 'subject': '数学'}, files={'file': ('a.html', b'x' * 21)}).status_code == 413
    monkeypatch.setattr(resources, 'MAX_UPLOAD', 10000)
    assert client.post('/admin/html-resources', data={'title': '课堂', 'subject': '数学'}, files={'file': ('a.zip', b'not zip')}).status_code == 422
    monkeypatch.setattr(resources, 'MAX_EXPANDED', 1)
    assert upload(client).status_code == 422


def test_backslash_paths_are_rejected():
    with pytest.raises(HTTPException):
        resources.safe_path("dir\\evil.html")


def test_full_application_routes_html_list_before_generic_admin_route(monkeypatch, tmp_path):
    from webgal_backend.app import app
    from webgal_backend import platform_admin
    monkeypatch.setattr(resources, 'settings', SimpleNamespace(jobs_dir=tmp_path))
    monkeypatch.setattr(resources, 'require_admin', lambda request: {'id': 'admin-user'})
    monkeypatch.setattr(platform_admin, 'require_admin', lambda request: {'id': 'admin-user'})
    client = TestClient(app)
    response = client.get('/admin/html-resources')
    assert response.status_code == 200, response.text
    assert response.json() == {'items': []}
    assert client.get('/admin/html-resources/taxonomy').json() == resources.TAXONOMY


def test_player_with_and_without_slash_uses_deployment_prefix(client):
    result = upload(client).json()
    identifier = result['id']
    for suffix in ['', '/']:
        response = client.get(f'/resources-play/{identifier}{suffix}')
        assert response.status_code == 200
        assert f'src="/forge/resources-play/{identifier}/files/lesson/index.html"' in response.text


def test_stage_without_grade_remains_filterable_by_existing_plaza(client):
    result = upload(client, stage='初中').json()
    assert result['payload']['grade'] == '初中'
    assert result['classification']['grade'] == ''
    assert '初中' in result['payload']['tags']
    assert upload(client, stage='小学', grade='四年级').json()['payload']['grade'] == '四年级'
    assert upload(client, stage='初中', grade='四年级').status_code == 422


def test_concurrent_publication_rejects_second_action_and_releases_lock(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    identifier = upload(client).json()['id']
    entered, release = Event(), Event()

    def delayed_archive(*args):
        entered.set()
        assert release.wait(5)
        return {'published': False}

    monkeypatch.setattr(resources, 'unpublish_work', delayed_archive)
    with ThreadPoolExecutor() as pool:
        archive = pool.submit(client.delete, f'/admin/html-resources/{identifier}/publication')
        try:
            assert entered.wait(5)
            conflict = client.post(f'/admin/html-resources/{identifier}/publication')
            assert conflict.status_code == 409
        finally:
            release.set()
        assert archive.result(timeout=5).status_code == 200
    assert resources.get_resource(identifier)[1]['state'] == 'archived'
    assert client.post(f'/admin/html-resources/{identifier}/publication').status_code == 200
    assert resources.get_resource(identifier)[1]['state'] == 'published'


def test_failed_publication_releases_lock(client, monkeypatch):
    from unittest.mock import Mock
    identifier = upload(client).json()['id']
    monkeypatch.setattr(resources, 'publish_work', Mock(side_effect=HTTPException(503, 'offline')))
    assert client.post(f'/admin/html-resources/{identifier}/publication').status_code == 503
    monkeypatch.setattr(resources, 'publish_work', lambda payload: {'published': True})
    assert client.post(f'/admin/html-resources/{identifier}/publication').status_code == 200


def test_zip_entry_autodetection_accepts_uppercase_extension(client):
    result = client.post('/admin/html-resources', data={'title': '课堂', 'subject': '数学'},
                         files={'file': ('lesson.zip', package({'lesson/INDEX.HTML': '<h1>课堂</h1>'}), 'application/zip')})
    assert result.status_code == 200
    assert result.json()['entry'] == 'lesson/INDEX.HTML'
