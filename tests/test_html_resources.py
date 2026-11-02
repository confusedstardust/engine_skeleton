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
    assert result['payload']['tags'] == ['IB', '小学', '科学', 'HTML互动资源']
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


@pytest.mark.parametrize('subject', ['', '[]'])
def test_subject_required_for_scalar_and_array_clients(client, subject):
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
    assert client.get('/admin/html-resources/taxonomy').json() == {**resources.TAXONOMY, 'custom': []}


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
    assert result['classification']['grade'] == []
    assert '初中' in result['payload']['tags']
    assert upload(client, stage='小学', grade='四年级').json()['payload']['grade'] == '四年级'
    assert upload(client, stage='初中', grade='四年级').status_code == 200


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


def test_missing_saved_page_assets_are_rejected_before_publication(client):
    response = client.post('/admin/html-resources', data={'title': '课堂', 'subject': '数学'},
                           files={'file': ('lesson.html', '<html><script src="lesson_files/app.js"></script><img src="lesson_files/a.png"></html>')})
    assert response.status_code == 422
    assert 'lesson_files/app.js' in response.json()['detail']
    assert 'ZIP' in response.json()['detail']
    assert client.get('/admin/html-resources').json() == {'items': []}


def test_saved_browser_script_extension_and_storage_bootstrap(client):
    response = client.post('/admin/html-resources', data={'title': '课堂', 'subject': '数学'},
                           files={'file': ('lesson.zip', package({'index.html': '<!doctype html><html><head><script src="assets/a.js.下载"></script></head></html>', 'assets/a.js.下载': 'localStorage.setItem("lesson", "saved")'}))})
    assert response.status_code == 200
    identifier = response.json()['id']
    root = f'/resources-play/{identifier}'
    page = client.get(root + '/files/index.html')
    assert page.text.index('Object.defineProperty(window, kind') < page.text.index('src="assets/a.js.')
    assert page.text.startswith('<!doctype html>')
    assert 'allow-same-origin' not in page.headers['content-security-policy']
    script = client.get(root + '/files/assets/a.js.下载')
    assert script.headers['content-type'].startswith('text/javascript')
    assert client.get(root + '/player.js').status_code == 200


def test_multiple_classification_and_custom_values_survive_publication(client):
    import json
    result = upload(client, subject=json.dumps(['科学', '地理']), grade=json.dumps(['四年级', '五年级']),
                    curriculum=json.dumps(['IB', 'AP']), stage=json.dumps(['小学', '初中']),
                    custom=json.dumps(['合作探究', '项目学习', '合作探究'])).json()
    assert result['classification']['subject'] == ['科学', '地理']
    assert result['classification']['custom'] == ['合作探究', '项目学习']
    assert len(result['payload']['tags']) > 8
    assert all(value in result['payload']['tags'] for value in ['科学', '地理', '四年级', '五年级', '小学', '初中', '合作探究'])


def test_edit_published_tags_updates_same_resource_and_remote_record(client, monkeypatch):
    from unittest.mock import Mock
    result = upload(client).json()
    identifier = result['id']
    publish = Mock(return_value={'published': True})
    monkeypatch.setattr(resources, 'publish_work', publish)
    response = client.patch(f'/admin/html-resources/{identifier}/tags', json={'classification': {
        'subject': ['历史', '语文'], 'grade': ['初一', '初二'], 'custom': ['人物分析']}})
    assert response.status_code == 200
    assert response.json()['id'] == identifier
    assert publish.call_args.args[0]['jobId'] == identifier
    assert publish.call_args.args[0]['subject'] == '历史'
    assert '语文' in publish.call_args.args[0]['tags']
    assert resources.get_resource(identifier)[1]['classification']['custom'] == ['人物分析']


def test_edit_archived_tags_keeps_resource_archived(client, monkeypatch):
    from unittest.mock import Mock
    identifier = upload(client).json()['id']
    assert client.delete(f'/admin/html-resources/{identifier}/publication').status_code == 200
    publish = Mock()
    monkeypatch.setattr(resources, 'publish_work', publish)
    response = client.patch(f'/admin/html-resources/{identifier}/tags', json={'classification': {'subject': ['自定义学科'], 'custom': ['自定义主题']}})
    assert response.status_code == 200 and response.json()['state'] == 'archived'
    publish.assert_not_called()
    assert client.get(f'/resources-play/{identifier}/').status_code == 404


def test_legacy_scalar_classification_normalizes_for_editing(client):
    identifier = upload(client).json()['id']
    root, data = resources.get_resource(identifier)
    data['classification'] = {'subject': '科学', 'stage': '小学', 'grade': '', 'curriculum': 'IB'}
    resources.write_json(root / 'metadata.json', data)
    listed = client.get('/admin/html-resources').json()['items'][0]
    assert listed['classification']['subject'] == ['科学']
    assert listed['classification']['grade'] == []
    assert listed['classification']['custom'] == []


@pytest.mark.parametrize('value', ['[1]', '[invalid', '["' + 'a' * 41 + '"]'])
def test_invalid_tag_inputs_are_rejected(client, value):
    assert upload(client, custom=value).status_code == 422


def test_edit_requires_subject_and_action_header(client):
    identifier = upload(client).json()['id']
    url = f'/admin/html-resources/{identifier}/tags'
    assert client.patch(url, json={'classification': {'subject': []}}).status_code == 422
    client.headers.pop('X-Forge-Admin-Action')
    assert client.patch(url, json={'classification': {'subject': ['科学']}}).status_code == 403


def test_custom_tags_are_reusable_and_truncated_portal_is_detected(client, monkeypatch):
    from unittest.mock import Mock
    identifier = upload(client, custom='场景探究').json()['id']
    assert '场景探究' in client.get('/admin/html-resources/taxonomy').json()['custom']
    monkeypatch.setattr(resources, 'publish_work', Mock(return_value={'published': True, 'work': {'tags': ['HTML互动资源']}}))
    response = client.patch(f'/admin/html-resources/{identifier}/tags', json={'classification': {'subject': ['科学', '地理'], 'custom': ['新标签']}})
    assert response.status_code == 409
    saved = resources.get_resource(identifier)[1]
    assert saved['state'] == 'publishing'
    assert saved['classification']['subject'] == ['科学', '地理']
    monkeypatch.setattr(resources, 'publish_work', lambda payload: {'published': True, 'work': payload})
    assert client.post(f'/admin/html-resources/{identifier}/publication').status_code == 200
