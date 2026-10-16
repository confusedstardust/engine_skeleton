import hashlib
import time
from unittest.mock import patch
from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from webgal_backend import platform_admin as admin


@pytest.fixture
def client(monkeypatch):
    salt=b'test-salt'
    digest=hashlib.scrypt(b'test-password',salt=salt,n=16384,r=8,p=1).hex()
    account={'id':'test-admin-id','username':'test-admin','password_hash':salt.hex()+':'+digest}
    sessions={}
    monkeypatch.setattr(admin,'admin_account',lambda username=None,user_id=None:dict(account) if account and (username=='test-admin' or user_id=='test-admin-id') else None)
    monkeypatch.setattr(admin,'save_session',lambda user_id,token:sessions.update({token:(user_id,time.time()+8*3600)}))
    monkeypatch.setattr(admin,'delete_session',lambda token:sessions.pop(token,None))
    monkeypatch.setattr(admin,'lookup_session',lambda token:{'id':sessions[token][0]} if account and token in sessions and sessions[token][1]>time.time() else None)
    admin._login_attempts.clear()
    app = FastAPI()
    app.include_router(admin.router)
    test_client=TestClient(app, headers={'X-Forge-Admin-Action': '1'})
    test_client.admin_account=account
    return test_client


def login(client):
    return client.post('/admin/login',json={'username':'test-admin','password':'test-password'})


@pytest.fixture
def ecosystem_game(client, monkeypatch, tmp_path):
    from types import SimpleNamespace
    from webgal_backend.storage import write_json
    from unittest.mock import Mock
    login(client)
    identifier = 'a' * 32
    root = tmp_path / identifier
    game = root / 'public/game'
    (game / 'scene').mkdir(parents=True)
    (game / 'config.txt').write_text('Game_name:课堂;')
    (game / 'scene/start.txt').write_text('课堂开始;')
    write_json(root / 'job.json', {'id': identifier, 'status': 'SUCCEEDED', 'title': '原作者课堂', 'options': {}, 'identity': {'user_id': 'original-author'}})
    owner = {'owner_user_id': 'original-author', 'author_id': 'original-author', 'nickname': '原作者', 'email': 'author@example.com'}
    calls = []
    class Cursor:
        def execute(self, sql, args=()):
            calls.append((sql, args))
        def fetchone(self):
            return dict(owner)
    @contextmanager
    def transaction():
        yield Cursor()
    monkeypatch.setattr(admin, 'database_transaction', transaction)
    monkeypatch.setattr(admin, 'settings', SimpleNamespace(jobs_dir=tmp_path))
    monkeypatch.setattr(admin, 'blocked', lambda *args: False)
    monkeypatch.setenv('WEBGAL_FRONTEND_URL', 'https://example.com/narrativeos')
    publish = Mock(return_value={'published': True, 'work': {'title': '原作者课堂'}})
    unpublish = Mock(return_value={'published': False})
    monkeypatch.setattr(admin, 'publish_work', publish)
    monkeypatch.setattr(admin, 'unpublish_work', unpublish)
    monkeypatch.setattr(admin, 'publication_status', lambda identifier: {'published': False})
    return SimpleNamespace(path=f'/admin/games/{identifier}/ecosystem-publication', root=root, owner=owner, calls=calls, publish=publish, unpublish=unpublish)


def test_admin_ecosystem_publish_preserves_original_author_and_audits_actor(client, ecosystem_game):
    import json
    game = ecosystem_game
    assert client.get(game.path).json()['owner_user_id'] == 'original-author'
    response = client.post(game.path)
    assert response.status_code == 200 and response.json()['published'] is True
    payload = game.publish.call_args.args[0]
    assert payload['ownerUserId'] == 'original-author'
    assert payload['authorName'] == '原作者'
    assert payload['title'] == '原作者课堂'
    assert payload['playUrl'] == 'https://example.com/narrativeos/play/' + 'a' * 32 + '/'
    audit = next(args for sql, args in game.calls if sql.startswith('INSERT INTO platform_admin_audit'))
    assert audit[1] == 'test-admin-id' and audit[4] == 'ECOSYSTEM_PUBLISH'
    assert json.loads(audit[6])['status'] == 'REQUESTED'
    assert any(sql.startswith('UPDATE platform_admin_audit') for sql, args in game.calls)


@pytest.mark.parametrize('reason', ['blocked', 'unbuilt', 'missing_author', 'missing_files'])
def test_admin_ecosystem_rejects_unpublishable_games(client, ecosystem_game, monkeypatch, reason):
    game = ecosystem_game
    if reason == 'blocked':
        monkeypatch.setattr(admin, 'blocked', lambda *args: True)
    elif reason == 'unbuilt':
        (game.root / 'public/game/config.txt').unlink()
    elif reason == 'missing_author':
        game.owner['author_id'] = None
    else:
        (game.root / 'job.json').unlink()
    assert client.post(game.path).status_code == 409
    game.publish.assert_not_called()


def test_admin_ecosystem_unpublish_works_for_blocked_game_without_local_files(client, ecosystem_game, monkeypatch):
    game = ecosystem_game
    monkeypatch.setattr(admin, 'blocked', lambda *args: True)
    (game.root / 'job.json').unlink()
    assert client.delete(game.path).status_code == 200
    game.unpublish.assert_called_once_with('original-author', 'a' * 32)


def test_admin_ecosystem_mutations_require_action_header(client, ecosystem_game):
    del client.headers['X-Forge-Admin-Action']
    assert client.post(ecosystem_game.path).status_code == 403
    assert client.delete(ecosystem_game.path).status_code == 403
    ecosystem_game.publish.assert_not_called()
    ecosystem_game.unpublish.assert_not_called()


def test_admin_ecosystem_service_failure_is_not_reported_as_success(client, ecosystem_game):
    ecosystem_game.publish.side_effect = admin.TeacherEcosystemError('服务暂时不可用')
    response = client.post(ecosystem_game.path)
    assert response.status_code == 503
    assert not any(sql.startswith('UPDATE platform_admin_audit') for sql, args in ecosystem_game.calls)


def test_ordinary_user_cannot_manage_ecosystem_publication(client):
    with patch('webgal_backend.auth.user_from_request', return_value={'id': 'ordinary', 'auth_type': 'sso'}):
        for method in ('get', 'post', 'delete'):
            assert getattr(client, method)('/admin/games/' + 'a' * 32 + '/ecosystem-publication').status_code == 403


@pytest.mark.parametrize('total,requested,expected_page,item_count,has_more', [
    (41, 2, 2, 20, True), (41, 99, 3, 1, False), (0, 1, 1, 0, False),
])
@pytest.mark.parametrize('owner_query,asset_status', [('', ''), ('原作者', 'ACTIVE'), ('author@example.com', 'BLOCKED')])
def test_filtered_listing_pagination(client, monkeypatch, total, requested, expected_page, item_count, has_more, owner_query, asset_status):
    login(client)
    calls = []
    class Cursor:
        def execute(self, sql, args=()):
            calls.append((sql, args))
        def fetchone(self):
            return {'total': total}
        def fetchall(self):
            return [{'id': str(i), 'name': '月夜河畔', 'status': 'ACTIVE', 'object_key': None}
                    for i in range(item_count)]
    @contextmanager
    def transaction():
        yield Cursor()
    monkeypatch.setattr(admin, 'database_transaction', transaction)
    response = client.get('/admin/assets', params={'search': '月夜', 'asset_kind': 'BACKGROUND', 'page': requested, 'owner_query': owner_query, 'asset_status': asset_status})
    assert response.status_code == 200
    data = response.json()
    assert data['total'] == total
    assert data['page'] == expected_page
    assert data['total_pages'] == max(1, (total + 19) // 20)
    assert data['has_more'] is has_more
    assert len(data['items']) == item_count
    # Count and data queries must apply the same search and kind filters.
    filters = ['月夜', '月夜', 'BACKGROUND'] + ([owner_query] * 3 if owner_query else []) + ([asset_status] if asset_status else [])
    assert calls[0][1] == filters
    assert calls[1][1] == ['ASSET', *filters, (expected_page - 1) * 20]
    assert 'CONVERT(r.id USING utf8mb4)' in calls[0][0]
    assert 'CONVERT(r.id USING utf8mb4)' in calls[1][0]


def test_listing_rejects_invalid_status_filter(client):
    login(client)
    assert client.get('/admin/assets?asset_status=INVALID').status_code == 422
    assert client.get('/admin/users?asset_status=ACTIVE').status_code == 422


def test_login_cookie_and_logout(client):
    r=login(client)
    assert r.status_code==200
    assert 'HttpOnly' in r.headers['set-cookie'] and 'SameSite=strict' in r.headers['set-cookie']
    assert client.get('/admin/me').status_code==200
    client.post('/admin/logout')
    with patch('webgal_backend.auth.user_from_request',return_value={'id':'ordinary','auth_type':'sso'}):
        assert client.get('/admin/me').status_code==403


def test_ordinary_user_cannot_list_or_mutate(client):
    with patch('webgal_backend.auth.user_from_request',return_value={'id':'ordinary','auth_type':'sso'}):
        assert client.get('/admin/assets').status_code==403
        assert client.patch('/admin/assets/example',json={'action':'block'}).status_code==403


def test_tampered_cookie_rejected(client):
    login(client)
    client.cookies.set(admin.COOKIE,'tampered')
    with patch('webgal_backend.auth.user_from_request',return_value={'id':'ordinary','auth_type':'sso'}):
        assert client.get('/admin/me').status_code==403


def test_expired_session_rejected(client):
    login(client)
    with patch('webgal_backend.platform_admin.time.time',return_value=time.time()+9*3600), patch('webgal_backend.auth.user_from_request',return_value={'id':'ordinary','auth_type':'sso'}):
        assert client.get('/admin/me').status_code==403


def test_login_rate_limited(client):
    for _ in range(5):
        assert client.post('/admin/login',json={'username':'test-admin','password':'wrong'}).status_code==401
    assert login(client).status_code==429


def test_disabled_admin_rejects_existing_session(client,monkeypatch):
    login(client)
    client.admin_account.clear()
    with patch('webgal_backend.auth.user_from_request',return_value={'id':'ordinary','auth_type':'sso'}):
        assert client.get('/admin/me').status_code==403


def test_asset_block_is_audited_in_same_transaction(client,monkeypatch):
    login(client)
    calls = []
    class Cursor:
        results = [{'id':'asset'}, {'status':'ACTIVE'}]
        def execute(self, sql, args=()):
            calls.append((sql,args))
        def fetchone(self):
            return self.results.pop(0)
    @contextmanager
    def transaction():
        yield Cursor()
    monkeypatch.setattr(admin, 'database_transaction', transaction)
    response=client.patch('/admin/assets/asset',json={'action':'block'})
    assert response.status_code==200
    assert any(sql.startswith('UPDATE assets') and args==('BLOCKED','asset') for sql,args in calls)
    assert any(sql.startswith('INSERT INTO platform_admin_audit') for sql,args in calls)


def test_modification_requires_action_header(client):
    login(client)
    del client.headers['X-Forge-Admin-Action']
    assert client.patch('/admin/assets/asset',json={'action':'block'}).status_code==403


def test_blocked_game_player_files_denied():
    from webgal_backend.app import app
    with patch('webgal_backend.app.admin_blocked',return_value=True):
        response=TestClient(app).get('/play/'+'a'*32+'/game/scene/start.txt')
        assert response.status_code==403


def test_game_detail_requires_admin_and_valid_id(client):
    with patch('webgal_backend.auth.user_from_request',return_value={'id':'ordinary','auth_type':'sso'}):
        assert client.get('/admin/games/'+'a'*32).status_code==403
    login(client)
    assert client.get('/admin/games/invalid-id').status_code==422


def test_dashboard_access_and_range_validation(client):
    with patch('webgal_backend.auth.user_from_request',return_value={'id':'ordinary','auth_type':'sso'}):
        assert client.get('/admin/dashboard').status_code==403
    login(client)
    assert client.get('/admin/dashboard?days=91').status_code==422
    assert client.get('/admin/dashboard?days=0').status_code==422
    with patch('webgal_backend.admin_metrics.dashboard_metrics',return_value={'days':7,'daily':[]}):
        assert client.get('/admin/dashboard?days=7').json()['days']==7


def test_game_detail_returns_configuration_and_keeps_blocked_preview_disabled(client,monkeypatch,tmp_path):
    from types import SimpleNamespace
    login(client)
    row={'id':'a'*32,'options_json':'{"mode":"advanced"}','status':'SUCCEEDED','source_material':'full original input'}
    class Cursor:
        def execute(self,*args): pass
        def fetchone(self): return dict(row)
    @contextmanager
    def transaction(): yield Cursor()
    monkeypatch.setattr(admin,'database_transaction',transaction)
    monkeypatch.setattr(admin,'blocked',lambda *args:True)
    monkeypatch.setattr(admin,'settings',SimpleNamespace(jobs_dir=tmp_path))
    scene=tmp_path/('a'*32)/'public/game/scene';scene.mkdir(parents=True)
    (scene/'start.txt').write_text('test')
    response=client.get('/admin/games/'+'a'*32)
    assert response.status_code==200
    game=response.json()['game']
    assert game['options']=={'mode':'advanced'}
    assert game['scene_count']==1 and game['can_preview'] is False


def test_admin_upload_rejects_invalid_file_and_ordinary_user(client):
    with patch('webgal_backend.auth.user_from_request',return_value={'id':'ordinary','auth_type':'sso'}):
        assert client.post('/admin/assets/upload',data={'kind':'BACKGROUND','name':'test'},files={'file':('x.png',b'bad','image/png')}).status_code==403
    login(client)
    assert client.post('/admin/assets/upload',data={'kind':'BACKGROUND','name':'test'},files={'file':('x.png',b'bad','image/png')}).status_code==422


def test_admin_upload_public_registration_and_failure_cleanup(client,monkeypatch):
    import io
    from PIL import Image
    from unittest.mock import MagicMock
    login(client)
    stream=io.BytesIO();Image.new('RGB',(2,2)).save(stream,format='PNG')
    bucket=MagicMock();bucket.put_object.return_value.etag='etag'
    monkeypatch.setattr(admin.AssetLibrary,'_bucket',lambda self:bucket)
    calls=[]
    class Cursor:
        def execute(self,sql,args=()):calls.append((sql,args))
    @contextmanager
    def transaction():yield Cursor()
    monkeypatch.setattr(admin,'database_transaction',transaction)
    response=client.post('/admin/assets/upload',data={'kind':'FIGURE','name':'人物','attributes':'{"era":["古代"],"clothing":["长袍"]}'},files={'file':('x.png',stream.getvalue(),'image/png')})
    assert response.status_code==200
    assert any("'UPLOADED','PUBLIC','ACTIVE'" in sql for sql,args in calls)
    assert any('before_json,after_json' in sql for sql,args in calls)
    import json
    stored=next(args for sql,args in calls if sql.startswith("INSERT INTO assets"))
    assert json.loads(stored[4])["attributes"]=={"era":["古代"],"clothing":["长袍"]}
    bucket.delete_object.assert_not_called()
    @contextmanager
    def failure():raise RuntimeError('db failure');yield
    monkeypatch.setattr(admin,'database_transaction',failure)
    with pytest.raises(RuntimeError):client.post('/admin/assets/upload',data={'kind':'FIGURE','name':'test'},files={'file':('x.png',stream.getvalue(),'image/png')})
    bucket.delete_object.assert_called_once()


def test_taxonomy_keeps_types_separate_and_reuses_saved_custom_labels(client,monkeypatch):
    login(client)
    class Cursor:
        def execute(self,*args):pass
        def fetchall(self):return [
            {'kind':'BGM','generation_metadata':{'category':'custom:片头','category_label':'片头','tags':['钢琴','循环']}},
            {'kind':'FIGURE','generation_metadata':'{"category":"ancient","category_label":"古代人物","tags":["男性"]}'}]
    @contextmanager
    def transaction():yield Cursor()
    monkeypatch.setattr(admin,'database_transaction',transaction)
    response=client.get('/admin/assets/taxonomy')
    assert response.status_code==200
    data=response.json()
    assert data['BGM']['categories']==[{'value':'custom:片头','label':'片头'}]
    assert data['BGM']['tags']==['钢琴','循环']
    assert data['FIGURE']['tags']==['男性']
    assert data['BACKGROUND']['tags']==[]


def test_grouped_attributes_single_choice_validation_and_storage(client,monkeypatch):
    from webgal_backend.asset_attributes import validate_attributes
    assert validate_attributes('BACKGROUND','{"style":["水墨"],"elements":["石头","桥"]}')=={'style':['水墨'],'elements':['石头','桥']}
    with pytest.raises(admin.HTTPException):validate_attributes('BACKGROUND','{"time":["白天","夜晚"]}')
    with pytest.raises(admin.HTTPException):validate_attributes('BGM','{"weather":["雨"]}')
    login(client)
    class Cursor:
        def execute(self,*args):pass
        def fetchall(self):return [{'kind':'BACKGROUND','generation_metadata':{'attributes':{'elements':['石头'],'time':['白天']},'tags':['石头','白天','无法确定的旧标签']}}]
    @contextmanager
    def transaction():yield Cursor()
    monkeypatch.setattr(admin,'database_transaction',transaction)
    grouped=client.get('/admin/assets/taxonomy').json()['BACKGROUND']['attributes']
    assert grouped=={'elements':['石头'],'time':['白天']}


def test_database_session_joins_current_role_and_block_state(monkeypatch):
    calls=[]
    class Cursor:
        def execute(self,sql,args):calls.append((sql,args))
        def fetchone(self):return {'id':'db-admin'}
    @contextmanager
    def transaction():yield Cursor()
    monkeypatch.setattr(admin,'database_transaction',transaction)
    assert admin.lookup_session('a'*64)=={'id':'db-admin'}
    sql,args=calls[0]
    assert "u.platform_role='ADMIN'" in sql
    assert 'COALESCE(c.blocked,0)=0' in sql
    assert 'expires_at>CURRENT_TIMESTAMP' in sql
    assert args==(hashlib.sha256(('a'*64).encode()).hexdigest(),)


def test_database_session_hash_storage_and_logout_revocation(monkeypatch):
    calls=[]
    class Cursor:
        def execute(self,sql,args):calls.append((sql,args))
    @contextmanager
    def transaction():yield Cursor()
    monkeypatch.setattr(admin,'database_transaction',transaction)
    token='a'*64
    admin.save_session('user-id',token)
    admin.delete_session(token)
    insert=next(args for sql,args in calls if sql.startswith('INSERT'))
    assert insert[1]=='user-id' and insert[2]==hashlib.sha256(token.encode()).hexdigest()
    assert calls[-1][0].startswith('DELETE FROM auth_sessions WHERE token_hash')
