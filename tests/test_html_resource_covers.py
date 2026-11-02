import io
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image
from fastapi import FastAPI
from fastapi.testclient import TestClient

from webgal_backend import html_resources as resources, html_resource_covers as covers, platform_admin, teacher_ecosystem


def image_bytes(color='red'):
    output = io.BytesIO()
    Image.new('RGB', (640, 480), color).save(output, 'PNG')
    return output.getvalue()


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(resources, 'settings', SimpleNamespace(jobs_dir=tmp_path))
    monkeypatch.setenv('WEBGAL_FRONTEND_URL', 'https://example.com/narrativeos')
    monkeypatch.setattr(resources, 'require_admin', lambda request: {'id': 'admin'})
    operation = lambda actor, identifier, owner, action, callback: callback()
    monkeypatch.setattr(resources, 'ecosystem_change', operation)
    monkeypatch.setattr(platform_admin, 'ecosystem_change', operation)
    publish = Mock(side_effect=lambda payload: {'published': True, 'work': dict(payload)})
    monkeypatch.setattr(resources, 'publish_work', publish)
    monkeypatch.setattr(resources, 'unpublish_work', lambda *args: {'published': False})
    sync = Mock(return_value={'updated': True})
    monkeypatch.setattr(teacher_ecosystem, 'update_work_cover', sync)
    monkeypatch.setattr(covers, 'capture', lambda *args: (covers.normalized_image(image_bytes()), 0))
    app = FastAPI(); app.include_router(resources.router)
    client = TestClient(app, headers={'X-Forge-Admin-Action': '1'})
    client.publish_mock = publish; client.cover_sync = sync
    return client


def upload(client):
    response = client.post('/admin/html-resources', data={'title': '封面课堂', 'subject': '科学'}, files={'file': ('lesson.html', '<h1>课堂</h1>')})
    assert response.status_code == 200
    return response.json()['id']


def test_upload_generates_cover_and_updates_only_cover_field(client):
    identifier = upload(client)
    root, metadata = resources.get_resource(identifier)
    assert metadata['cover_status'] == 'ready'
    assert metadata['cover_source'] == 'automatic'
    assert metadata['state'] == 'published'
    assert client.publish_mock.call_count == 1
    client.cover_sync.assert_called_once_with('admin', identifier, metadata['payload']['coverUrl'])
    path = metadata['payload']['coverUrl'].split('/narrativeos')[-1]
    response = client.get(path)
    assert response.status_code == 200 and response.headers['content-type'] == 'image/webp'
    assert Image.open(io.BytesIO(response.content)).size == (1280, 720)
    assert client.get(f'/resources-play/{identifier}/cover/wrong.webp').status_code == 404


def test_manual_replacement_changes_url_and_invalidates_older_job(client):
    identifier = upload(client)
    root, before = resources.get_resource(identifier)
    old_revision = before['cover_revision']
    response = client.post(f'/admin/html-resources/{identifier}/cover', files={'file': ('cover.png', image_bytes('blue'))})
    assert response.status_code == 200
    updated = response.json()
    assert updated['cover_source'] == 'manual'
    assert updated['payload']['coverUrl'] != before['payload']['coverUrl']
    covers.save_cover({'id': 'admin'}, identifier, covers.normalized_image(image_bytes()), revision=old_revision)
    assert resources.get_resource(identifier)[1]['payload']['coverUrl'] == updated['payload']['coverUrl']


def test_failed_capture_keeps_previous_cover_and_can_retry(client, monkeypatch):
    identifier = upload(client)
    before = resources.get_resource(identifier)[1]['payload']['coverUrl']
    monkeypatch.setattr(covers, 'capture', Mock(side_effect=RuntimeError('browser unavailable')))
    assert client.post(f'/admin/html-resources/{identifier}/cover/generate').status_code == 202
    record = resources.get_resource(identifier)[1]
    assert record['cover_status'] == 'failed' and record['payload']['coverUrl'] == before
    monkeypatch.setattr(covers, 'capture', lambda *args: (covers.normalized_image(image_bytes()), 0))
    client.post(f'/admin/html-resources/{identifier}/cover/generate')
    assert resources.get_resource(identifier)[1]['cover_status'] == 'ready'


def test_sync_failure_is_visible_and_retry_does_not_recapture(client, monkeypatch):
    identifier = upload(client)
    client.cover_sync.side_effect = RuntimeError('portal offline')
    response = client.post(f'/admin/html-resources/{identifier}/cover', files={'file': ('cover.png', image_bytes())})
    assert response.json()['cover_status'] == 'sync_failed'
    assert response.json()['state'] == 'published'
    client.cover_sync.side_effect = None
    monkeypatch.setattr(covers, 'capture', Mock(side_effect=AssertionError('must not capture')))
    assert client.post(f'/admin/html-resources/{identifier}/cover/sync').json()['cover_status'] == 'ready'


def test_archived_cover_replacement_does_not_publish(client):
    identifier = upload(client)
    client.delete(f'/admin/html-resources/{identifier}/publication')
    client.cover_sync.reset_mock()
    response = client.post(f'/admin/html-resources/{identifier}/cover', files={'file': ('cover.png', image_bytes())})
    assert response.json()['state'] == 'archived'
    client.cover_sync.assert_not_called()
    path = response.json()['payload']['coverUrl'].split('/narrativeos')[-1]
    assert client.get(path).status_code == 404


def test_invalid_image_and_csrf_are_rejected(client):
    identifier = upload(client)
    assert client.post(f'/admin/html-resources/{identifier}/cover', files={'file': ('cover.png', b'not an image')}).status_code == 422
    client.headers.pop('X-Forge-Admin-Action')
    assert client.post(f'/admin/html-resources/{identifier}/cover/generate').status_code == 403


@pytest.mark.parametrize('address', ['127.0.0.1', '10.0.0.2', '169.254.169.254', '::1', '198.18.0.1'])
def test_renderer_never_fetches_private_addresses(monkeypatch, address):
    monkeypatch.setattr(covers.socket, 'getaddrinfo', lambda *args, **kwargs: [(2, 1, 6, '', (address, 443))])
    with pytest.raises(ValueError, match='内网'):
        covers.public_asset('https://untrusted.example/a.png', 1024)


def test_renderer_rejects_non_http_and_custom_ports():
    for url in ['file:///etc/passwd', 'ftp://example.com/a', 'https://example.com:8010/a']:
        with pytest.raises(ValueError): covers.public_asset(url, 1024)


def test_backfill_skips_existing_and_archived(client, monkeypatch):
    existing = upload(client); archived = upload(client); missing = upload(client)
    client.delete(f'/admin/html-resources/{archived}/publication')
    root, metadata = resources.get_resource(missing)
    metadata['payload']['coverUrl'] = None
    resources.write_json(root / 'metadata.json', metadata)
    generate = Mock(return_value={'cover_status': 'ready'})
    monkeypatch.setattr(covers, 'generate_cover', generate)
    covers.backfill()
    generate.assert_called_once_with({'id': 'admin'}, missing, only_missing=True)


def test_external_redirect_to_private_address_is_blocked(monkeypatch):
    resolves=[]; connections=[]
    def dns(host, *args, **kwargs):
        resolves.append(host)
        return [(2, 1, 6, '', ('127.0.0.1' if host=='private.example' else '8.8.8.8', 443))]
    class Connection:
        def __init__(self, host, port, timeout): connections.append(host)
        def request(self, *args, **kwargs): pass
        def getresponse(self): return SimpleNamespace(status=302, getheader=lambda name, default='':'https://private.example/secret')
        def close(self): pass
    monkeypatch.setattr(covers.socket, 'getaddrinfo', dns)
    monkeypatch.setattr(covers, 'HTTPSConnection', Connection)
    with pytest.raises(ValueError, match='内网'):
        covers.public_asset('https://public.example/image.png',1024)
    assert connections == ['public.example']


def test_external_fetch_pins_tcp_and_does_not_send_credentials(monkeypatch):
    calls={}
    monkeypatch.setattr(covers.socket, 'getaddrinfo', lambda *args, **kwargs:[(2,1,6,'',('8.8.8.8',443))])
    monkeypatch.setattr(covers.socket, 'create_connection', lambda address, timeout, source:calls.update(address=address))
    class Connection:
        def __init__(self, host, port, timeout): calls.update(host=host)
        def request(self, method, path, headers):
            self._create_connection(('rebound.example',443),4)
            calls.update(headers=headers,method=method)
        def getresponse(self): return SimpleNamespace(status=200,read=lambda size:b'image',getheader=lambda name, default='':'image/png')
        def close(self): pass
    monkeypatch.setattr(covers, 'HTTPSConnection', Connection)
    assert covers.public_asset('https://public.example/image.png',1024)[1] == b'image'
    assert calls['host'] == 'public.example' and calls['address'] == ('8.8.8.8',443)
    assert 'Authorization' not in calls['headers'] and 'Cookie' not in calls['headers']
