from contextlib import nullcontext
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
    monkeypatch.setattr(resources, 'database_transaction', lambda: nullcontext(SimpleNamespace(execute=lambda *args: None, fetchall=lambda: [])))
    monkeypatch.setattr(resources, 'ecosystem_change', lambda actor, identifier, owner, action, operation: operation())
    monkeypatch.setenv('WEBGAL_FRONTEND_URL', 'https://example.com/forge')
    monkeypatch.setattr(resources, 'publish_work', lambda payload: {'published': True, 'work': payload})
    monkeypatch.setattr(resources, 'unpublish_work', lambda *args: {'published': False})
    monkeypatch.setattr(resources, 'update_work_details', lambda payload: {'updated': True})
    from webgal_backend import html_resource_covers
    monkeypatch.setattr(html_resource_covers, 'generate_cover', lambda *args, **kwargs: None)
    app = FastAPI()
    app.include_router(resources.router)
    return TestClient(app, headers={'X-Forge-Admin-Action': '1'})


def upload(client, **overrides):
    return client.post('/admin/html-resources', data={'title': '行星实验室', 'subject': '科学', 'curriculum': 'IB', 'stage': '小学', **overrides},
                       files={'file': ('lesson.zip', package({'lesson/index.html': '<script src="app.js"></script>', 'lesson/app.js': 'window.ready=true;'}), 'application/zip')})


def edit_values(**overrides):
    import json
    return {'title': '新版课堂', 'summary': '新的简介', 'featured': 'true',
            'classification': json.dumps({'subject': ['数学', '科学'], 'stage': ['初中']}), **overrides}


def test_edit_details_and_featured_sync_without_republishing(client, monkeypatch):
    item = upload(client).json()
    calls = []
    monkeypatch.setattr(resources, 'update_work_details', lambda payload: calls.append(dict(payload)) or {'updated': True})
    monkeypatch.setattr(resources, 'publish_work', lambda payload: pytest.fail('edit must not republish'))
    response = client.patch(f"/admin/html-resources/{item['id']}", data=edit_values())
    assert response.status_code == 200
    saved = response.json()
    assert saved['payload']['title'] == '新版课堂'
    assert saved['payload']['featured'] is True
    assert saved['classification']['subject'] == ['数学', '科学']
    assert saved['created_at'] == item['created_at'] and saved['state'] == 'published'
    assert calls[0]['summary'] == '新的简介'
    assert client.patch(f"/admin/html-resources/{item['id']}/featured", json={'featured': False}).status_code == 200
    assert calls[-1]['featured'] is False


def test_archived_edit_keeps_resource_archived(client, monkeypatch):
    item = upload(client).json()
    client.delete(f"/admin/html-resources/{item['id']}/publication")
    monkeypatch.setattr(resources, 'update_work_details', lambda payload: pytest.fail('archived edits stay local'))
    response = client.patch(f"/admin/html-resources/{item['id']}", data=edit_values())
    assert response.json()['state'] == 'archived'
    assert client.get(f"/resources-play/{item['id']}/").status_code == 404


def test_package_replacement_is_validated_before_switching_files(client):
    item = upload(client).json()
    url = f"/admin/html-resources/{item['id']}"
    bad = client.patch(url, data=edit_values(), files={'file': ('lesson.zip', package({'index.html': '<script src="missing.js"></script>'}), 'application/zip')})
    assert bad.status_code == 422
    assert client.get(f"/resources-play/{item['id']}/files/lesson/app.js").text == 'window.ready=true;'
    good = client.patch(url, data=edit_values(), files={'file': ('new.html', '<h1>新的课堂</h1>', 'text/html')})
    assert good.status_code == 200 and good.json()['entry'] == 'index.html'
    assert '新的课堂' in client.get(f"/resources-play/{item['id']}/files/index.html").text


def test_edit_auth_validation_and_uncertain_sync(client, monkeypatch):
    item = upload(client).json()
    url = f"/admin/html-resources/{item['id']}"
    assert client.patch(url, data=edit_values(title=' ')).status_code == 422
    assert client.patch(url, data=edit_values(entry='../escape.html')).status_code == 422
    assert client.patch(url, data=edit_values(classification='[]')).status_code == 422
    client.headers.pop('X-Forge-Admin-Action')
    assert client.patch(url, data=edit_values()).status_code == 403
    assert client.patch(url+'/featured', json={'featured': True}).status_code == 403
    client.headers['X-Forge-Admin-Action'] = '1'
    def unavailable(payload):
        raise HTTPException(503, 'plaza unavailable')
    monkeypatch.setattr(resources, 'update_work_details', unavailable)
    assert client.patch(url, data=edit_values()).status_code == 503
    saved = client.get('/admin/html-resources').json()['items'][0]
    assert saved['payload']['title'] == '新版课堂' and saved['metadata_sync_error']
    monkeypatch.setattr(resources, 'update_work_details', lambda payload: {'updated': True})
    assert 'metadata_sync_error' not in client.patch(url, data=edit_values()).json()


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


def test_explicit_resource_capabilities_keep_opaque_origin(client):
    import json
    result = client.post('/admin/html-resources', data={'title':'打印工具','subject':'跨学科'}, files={'file':('tool.zip', package({'index.html':'<h1>tool</h1>','narrativeos-resource.json':json.dumps({'capabilities':['print','png-export']})}), 'application/zip')})
    assert result.status_code == 200
    item = result.json()
    assert item['capabilities'] == ['print','png-export']
    player = client.get(f"/resources-play/{item['id']}/")
    assert 'sandbox="allow-scripts allow-downloads allow-modals"' in player.text
    assert 'allow-same-origin' not in player.text
    file = client.get(f"/resources-play/{item['id']}/files/index.html")
    assert 'allow-modals' in file.headers['content-security-policy']
    assert 'allow-same-origin' not in file.headers['content-security-policy']
    assert client.get(f"/resources-play/{item['id']}/capabilities.js").status_code == 200
    # Replacing the package without a manifest removes the extra capabilities.
    updated = client.patch(f"/admin/html-resources/{item['id']}", data=edit_values(), files={'file':('new.html','<h1>plain</h1>','text/html')})
    assert updated.status_code == 200 and updated.json()['capabilities'] == []
    assert 'allow-modals' not in client.get(f"/resources-play/{item['id']}/").text


@pytest.mark.parametrize('manifest', ['[]', '{bad', '{"capabilities":["same-origin"]}', '{"capabilities":"microphone"}'])
def test_invalid_capability_manifest_is_rejected_before_publication(client, manifest):
    result = client.post('/admin/html-resources', data={'title':'工具','subject':'科学'}, files={'file':('tool.zip',package({'index.html':'<h1>tool</h1>','narrativeos-resource.json':manifest}),'application/zip')})
    assert result.status_code == 422
    assert not list(resources.resource_root().glob('*/metadata.json'))


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


def test_html_practice_tool_requires_published_resource_and_action_header(client, monkeypatch):
    saved = upload(client).json()
    identifier = saved['id']
    url = f'/admin/html-resources/{identifier}/practice-tool'
    calls = []
    selected = set()

    def save(actor, job_id, enabled):
        calls.append((actor['id'], job_id, enabled))
        (selected.add if enabled else selected.discard)(job_id)
        return {'is_practice_tool': enabled}

    monkeypatch.setattr(resources, 'save_practice_tool', save)
    monkeypatch.setattr(resources, 'database_transaction', lambda: nullcontext(SimpleNamespace(
        execute=lambda *args: None, fetchall=lambda: [{'job_id': job_id} for job_id in selected],
    )))
    assert client.put(url, json={'enabled': True}, headers={'X-Forge-Admin-Action': '0'}).status_code == 403
    assert client.put(url, json={'enabled': 'true'}).status_code == 422
    assert client.put(url, json={'enabled': True}).json() == {'is_practice_tool': True}
    assert client.get('/admin/html-resources').json()['items'][0]['is_practice_tool'] is True
    assert client.put(url, json={'enabled': False}).json() == {'is_practice_tool': False}
    assert client.get('/admin/html-resources').json()['items'][0]['is_practice_tool'] is False
    assert client.delete(f'/admin/html-resources/{identifier}/publication').status_code == 200
    assert client.put(url, json={'enabled': True}).status_code == 409
    assert calls == [('admin-user', identifier, True), ('admin-user', identifier, False)]


def test_practice_list_hides_missing_and_archived_html(monkeypatch):
    import webgal_backend.app as backend

    rows = [
        {'job_id': job_id, 'play_url': f'https://example.com/forge/{kind}/{job_id}/'}
        for job_id, kind in [('game', 'play'), ('live', 'resources-play'),
                             ('archived', 'resources-play'), ('missing', 'resources-play')]
    ]
    monkeypatch.setattr(backend, 'database_transaction', lambda: nullcontext(SimpleNamespace(
        execute=lambda *args: None, fetchall=lambda: rows,
    )))

    def lookup(job_id):
        if job_id == 'missing':
            raise HTTPException(404)
        return None, {'state': 'published' if job_id == 'live' else 'archived'}

    monkeypatch.setattr(backend, 'get_html_resource', lookup)
    response = TestClient(backend.app).get('/practice-tools')
    assert response.status_code == 200
    assert [row['job_id'] for row in response.json()['items']] == ['game', 'live']
