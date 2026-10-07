from __future__ import annotations

import json
import uuid
import hashlib
import hmac
import secrets
import time
import threading
import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response, Query, UploadFile, File, Form
from pydantic import BaseModel, Field

from .asset_library import AssetLibrary, _public_url, _location_hash
from .config import settings

router = APIRouter(prefix='/admin', tags=['platform-admin'])
TABLES = {'games': ('generation_jobs', 'JOB'), 'assets': ('assets', 'ASSET'), 'users': ('users', 'USER')}
COOKIE = 'forge_platform_admin'
_login_attempts = {}
_login_lock = threading.Lock()


def require_action_header(request):
    if request.headers.get('x-forge-admin-action') != '1':
        raise HTTPException(403, '无效管理请求')


def password_matches(password, value):
    try:
        salt, digest = value.split(':', 1)
        candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
        return hmac.compare_digest(candidate, digest)
    except (ValueError, TypeError, AttributeError):
        return False


def admin_account(*, username=None, user_id=None):
    field,value=('username',username) if username is not None else ('id',user_id)
    with AssetLibrary()._transaction() as cursor:
        cursor.execute(f"SELECT u.id,u.username,u.password_hash FROM users u LEFT JOIN platform_resource_controls c ON c.resource_type='USER' AND BINARY c.resource_id=BINARY u.id WHERE u.{field}=%s AND u.platform_role='ADMIN' AND COALESCE(c.blocked,0)=0",(value,))
        return cursor.fetchone()


def save_session(user_id, token):
    with AssetLibrary()._transaction() as cursor:
        cursor.execute('DELETE FROM auth_sessions WHERE user_id=%s AND expires_at<=CURRENT_TIMESTAMP(3)',(user_id,))
        cursor.execute('INSERT INTO auth_sessions (id,user_id,token_hash,expires_at) VALUES (%s,%s,%s,DATE_ADD(CURRENT_TIMESTAMP(3),INTERVAL 8 HOUR))',(uuid.uuid4().hex,user_id,hashlib.sha256(token.encode()).hexdigest()))


def delete_session(token):
    if not token:return
    with AssetLibrary()._transaction() as cursor:
        cursor.execute('DELETE FROM auth_sessions WHERE token_hash=%s',(hashlib.sha256(token.encode()).hexdigest(),))


def lookup_session(token):
    with AssetLibrary()._transaction() as cursor:
        cursor.execute("SELECT u.id FROM auth_sessions s JOIN users u ON u.id=s.user_id LEFT JOIN platform_resource_controls c ON c.resource_type='USER' AND BINARY c.resource_id=BINARY u.id WHERE s.token_hash=%s AND s.expires_at>CURRENT_TIMESTAMP(3) AND u.platform_role='ADMIN' AND COALESCE(c.blocked,0)=0",(hashlib.sha256(token.encode()).hexdigest(),))
        row=cursor.fetchone()
    return row


def session_user(request):
    token=request.cookies.get(COOKIE,'')
    if not re.fullmatch(r'[0-9a-f]{64}',token):return None
    row=lookup_session(token)
    return {'id':row['id'],'auth_type':'platform_admin'} if row else None


class Login(BaseModel):
    username: str = Field(max_length=191)
    password: str = Field(max_length=512)


@router.post('/login')
def login(payload: Login, request: Request, response: Response):
    require_action_header(request)
    key = request.client.host if request.client else 'unknown'
    now = time.time()
    with _login_lock:
        expired = [k for k,v in _login_attempts.items() if now-v[0] > 300]
        for k in expired:
            _login_attempts.pop(k, None)
        started, attempts = _login_attempts.get(key, (now, 0))
        if attempts >= 5 or len(_login_attempts) >= 1000:
            raise HTTPException(429, '尝试次数过多，请五分钟后重试')
        _login_attempts[key] = (started, attempts+1)
    account=admin_account(username=payload.username.strip())
    # Perform the same password work for unknown accounts.
    value=account['password_hash'] if account else '00:'+'0'*128
    valid_password = password_matches(payload.password,value)
    if not account or not valid_password:
        raise HTTPException(401, '账号或密码错误')
    with _login_lock:
        _login_attempts.pop(key, None)
    token=secrets.token_hex(32)
    save_session(account['id'],token)
    response.set_cookie(COOKIE, token, max_age=8*3600, httponly=True, samesite='strict', secure=request.url.scheme=='https' or request.headers.get('x-forwarded-proto')=='https', path='/')
    return {'admin': True}


@router.post('/logout')
def logout(request: Request, response: Response):
    require_action_header(request)
    delete_session(request.cookies.get(COOKIE,''))
    response.delete_cookie(COOKIE, path='/')
    return {'logged_out': True}


def is_admin(user):
    return user.get('auth_type') == 'sso' and admin_account(user_id=user.get('id')) is not None


def require_admin(request):
    local = session_user(request)
    if local:
        return local
    from .auth import user_from_request
    user = user_from_request(request, settings.workspace_root)
    if not is_admin(user):
        raise HTTPException(403, '仅管理员可访问')
    return user


def blocked(kind, identifier):
    with AssetLibrary()._transaction() as cursor:
        cursor.execute('SELECT blocked FROM platform_resource_controls WHERE resource_type=%s AND resource_id=%s', (kind, identifier))
        row = cursor.fetchone()
        return bool(row and row['blocked'])


@router.get('/me')
def me(request: Request):
    require_admin(request)
    return {'admin': True}


@router.get('/dashboard')
def dashboard(request: Request, days: int = Query(default=30, ge=1, le=90)):
    require_admin(request)
    from .admin_metrics import dashboard_metrics
    return dashboard_metrics(days)


@router.get('/games/{identifier}')
def game_detail(identifier: str, request: Request):
    require_admin(request)
    if not re.fullmatch(r'[0-9a-f]{32}', identifier):
        raise HTTPException(422, '无效作品 ID')
    with AssetLibrary()._transaction() as cursor:
        cursor.execute('''SELECT id,owner_user_id,source_material,status,phase,progress_percent,
            draft_revision,published_revision,build_state,options_json,error_code,error_message,
            created_at,updated_at,started_at,finished_at FROM generation_jobs WHERE id=%s''', (identifier,))
        row = cursor.fetchone()
        if row is None:
            raise HTTPException(404, '作品不存在')
    row['blocked'] = blocked('JOB', identifier)
    options = row.pop('options_json', None)
    row['options'] = json.loads(options) if isinstance(options, str) else options
    root = settings.jobs_dir / identifier
    row['scene_count'] = len(list((root / 'public/game/scene').glob('*.txt')))
    row['image_count'] = sum(len(list((root / 'public/game' / directory).glob('*.webp'))) for directory in ('background', 'figure'))
    row['can_preview'] = row['status'] == 'SUCCEEDED' and row['scene_count'] > 0 and not row['blocked']
    return {'game': row}


@router.get('/assets/taxonomy')
def asset_taxonomy(request: Request):
    require_admin(request)
    result={kind:{'categories':[], 'tags':[], 'attributes':{}} for kind in ('BACKGROUND','FIGURE','BGM')}
    with AssetLibrary()._transaction() as cursor:
        cursor.execute("SELECT DISTINCT kind, generation_metadata FROM assets WHERE visibility='PUBLIC' AND status<>'DELETED' AND generation_metadata IS NOT NULL")
        rows=cursor.fetchall()
    for row in rows:
        if row['kind'] not in result:
            continue
        metadata=row['generation_metadata']
        if isinstance(metadata,str):
            metadata=json.loads(metadata)
        if not isinstance(metadata,dict):
            continue
        entry=result[row['kind']]
        from .asset_attributes import GROUPS
        schema={g['key']:g for g in GROUPS[row['kind']]}
        grouped=metadata.get('attributes',{})
        if isinstance(grouped,dict):
            for key,values in grouped.items():
                if key in schema and isinstance(values,list):
                    dest=entry['attributes'].setdefault(key,[])
                    for value in values:
                        if isinstance(value,str) and value not in dest:dest.append(value)
        # Legacy labels are reused only when their dimension is unambiguous.
        for value in metadata.get('tags',[]) if isinstance(metadata.get('tags'),list) else []:
            matches=[g['key'] for g in schema.values() if value in g['options']]
            if len(matches)==1:
                dest=entry['attributes'].setdefault(matches[0],[])
                if value not in dest:dest.append(value)

        category=metadata.get('category')
        label=metadata.get('category_label')
        if isinstance(category,str) and isinstance(label,str) and category and label and not any(c['value']==category for c in entry['categories']):
            entry['categories'].append({'value':category,'label':label})
        tags=metadata.get('tags',[])
        if isinstance(tags,list):
            for tag in tags:
                if isinstance(tag,str) and tag and tag not in entry['tags']:
                    entry['tags'].append(tag)
    return result


@router.post('/assets/upload')
async def upload_asset(request: Request, file: UploadFile = File(...), kind: str = Form(...), name: str = Form(...), category: str = Form(''), category_label: str = Form(''), tags: str = Form('[]'), attributes: str = Form('{}')):
    require_action_header(request)
    actor = require_admin(request)
    if kind not in {'BACKGROUND','FIGURE','VOICE','BGM'} or not name.strip() or len(name.strip()) > 200:
        raise HTTPException(422, '请提供有效名称和素材类型')
    try:
        labels = json.loads(tags)
        if not isinstance(labels, list) or len(labels) > 20 or any(not isinstance(t,str) or len(t)>40 for t in labels):
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(422, '标签格式无效')
    from .asset_attributes import validate_attributes, CATEGORY_IDS
    grouped=validate_attributes(kind,attributes)
    if grouped:
        labels=list(dict.fromkeys(v for values in grouped.values() for v in values))
        primary=(grouped.get('place') or grouped.get('identity') or grouped.get('usage') or [])
        category_label=primary[0] if primary else ''
        category=CATEGORY_IDS.get(category_label,'custom:'+category_label) if category_label else ''
    content = await file.read(30*1024*1024+1)
    if not content or len(content)>30*1024*1024:
        raise HTTPException(422, '文件不能为空，且不能超过 30 MB')
    import io
    import mimetypes
    from pathlib import Path
    extension = Path(file.filename or '').suffix.lower()
    width = height = None
    if kind in {'BACKGROUND','FIGURE'}:
        from PIL import Image
        try:
            with Image.open(io.BytesIO(content)) as image:
                width,height=image.size
                image.verify()
                fmt=image.format
            extension={'PNG':'.png','JPEG':'.jpg','WEBP':'.webp'}[fmt]
        except Exception:
            raise HTTPException(422, '请选择有效的 PNG、JPEG 或 WebP 图片')
    elif not ((extension=='.mp3' and (content.startswith(b'ID3') or len(content)>1 and content[0]==255 and content[1]&224==224)) or (extension=='.wav' and content[:4]==b'RIFF' and content[8:12]==b'WAVE') or (extension=='.ogg' and content[:4]==b'OggS') or (extension=='.m4a' and content[4:8]==b'ftyp')):
        raise HTTPException(422, '请选择有效的 MP3、WAV、OGG 或 M4A 音频')
    library=AssetLibrary()
    aid,fid=uuid.uuid4().hex,uuid.uuid4().hex
    key=f"{settings.oss_prefix.rstrip('/')}/public_assets/admin/{aid}/original{extension}"
    mime=mimetypes.guess_type('asset'+extension)[0] or 'application/octet-stream'
    bucket=library._bucket()
    result=bucket.put_object(key,content,headers={'Content-Type':mime})
    metadata={'library_scope':'PLATFORM','category':category[:80],'category_label':category_label[:80],'tags':labels,'attributes':grouped,'uploaded_by':actor['id']}
    try:
        with library._transaction() as cursor:
            owner='platform-public-assets'
            cursor.execute("INSERT INTO users (id,nickname,updated_at) VALUES (%s,'平台素材库',CURRENT_TIMESTAMP(3)) ON DUPLICATE KEY UPDATE id=id",(owner,))
            cursor.execute("INSERT INTO assets (id,owner_user_id,name,kind,source_type,visibility,status,generation_metadata,source_key) VALUES (%s,%s,%s,%s,'UPLOADED','PUBLIC','ACTIVE',%s,%s)",(aid,owner,name.strip(),kind,json.dumps(metadata,ensure_ascii=False),'admin-upload:'+aid))
            cursor.execute("INSERT INTO asset_files (id,asset_id,revision,variant,storage_provider,bucket,region,object_key,location_hash,sha256,etag,mime_type,size_bytes,width_px,height_px,status,uploaded_at) VALUES (%s,%s,1,'original','OSS',%s,'oss-cn-hangzhou',%s,%s,%s,%s,%s,%s,%s,%s,'READY',CURRENT_TIMESTAMP(3))",(fid,aid,settings.oss_bucket,key,_location_hash('OSS',settings.oss_bucket,key),hashlib.sha256(content).hexdigest(),getattr(result,'etag',None),mime,len(content),width,height))
            cursor.execute('INSERT INTO platform_admin_audit (id,actor_user_id,resource_type,resource_id,action,before_json,after_json) VALUES (%s,%s,%s,%s,%s,%s,%s)',(uuid.uuid4().hex,actor['id'],'ASSET',aid,'upload','{}',json.dumps(metadata)))
    except Exception:
        bucket.delete_object(key)
        raise
    return {'asset_id':aid,'url':_public_url(key)}


@router.get('/{resource}')
def listing(resource: str, request: Request, page: int = 1, search: str = '', asset_kind: str = ''):
    require_admin(request)
    if resource not in TABLES or page < 1:
        raise HTTPException(422, '无效查询')
    if asset_kind and asset_kind not in {'BACKGROUND','FIGURE','VOICE','BGM'}:
        raise HTTPException(422, '无效素材类型')
    table, kind = TABLES[resource]
    columns = {'games': 'r.id,LEFT(r.source_material,48) AS name,r.owner_user_id,r.status,r.phase,r.created_at',
               'assets': "r.id,r.name,r.kind,r.owner_user_id,r.source_type,r.visibility,r.status,r.created_at,(SELECT f.object_key FROM asset_files f WHERE f.asset_id=r.id AND f.variant='original' AND f.status='READY' AND f.mime_type LIKE 'image/%%' ORDER BY f.revision DESC LIMIT 1) AS object_key",
               'users': 'r.id,r.email,r.nickname,r.created_at'}[resource]
    if resource != 'users':
        columns += ',u.email AS owner_email'
    field = {'games': "CONCAT(r.owner_user_id,' ',COALESCE(u.email,''),' ',r.source_material)", 'assets': 'r.name', 'users': "CONCAT(COALESCE(r.email,''),' ',COALESCE(r.nickname,''))"}[resource]
    owner_join = ' LEFT JOIN users u ON u.id=r.owner_user_id' if resource != 'users' else ''
    kind_where = ' AND r.kind=%s' if resource == 'assets' and asset_kind else ''
    parameters = [kind, search, search] + ([asset_kind] if kind_where else []) + [(page-1)*20]
    with AssetLibrary()._transaction() as cursor:
        cursor.execute(f"SELECT {columns},COALESCE(c.blocked,0) AS blocked FROM {table} r{owner_join} LEFT JOIN platform_resource_controls c ON c.resource_type=%s AND BINARY c.resource_id=BINARY r.id WHERE (LOCATE(%s,r.id)>0 OR LOCATE(%s,{field})>0) {kind_where} ORDER BY r.created_at DESC,r.id LIMIT 21 OFFSET %s", parameters)
        rows = cursor.fetchall()
    if resource == 'assets':
        for row in rows:
            row['blocked'] = row['status'] == 'BLOCKED'
            key = row.pop('object_key', None)
            row['url'] = _public_url(key) if key else None
    return {'items': rows[:20], 'has_more': len(rows) > 20}


class Change(BaseModel):
    action: Literal['block', 'restore', 'rename']
    name: str = Field(default='', max_length=200)


@router.patch('/{resource}/{identifier}')
def change(resource: str, identifier: str, payload: Change, request: Request):
    require_action_header(request)
    actor = require_admin(request)
    if resource not in TABLES:
        raise HTTPException(422, '无效资源')
    table, kind = TABLES[resource]
    if resource == 'users' and identifier == actor['id'] and payload.action == 'block':
        raise HTTPException(422, '不能禁用当前管理员')
    if payload.action == 'rename' and (resource == 'games' or not payload.name.strip()):
        raise HTTPException(422, '请输入有效名称')
    if resource == 'users' and payload.action == 'rename' and len(payload.name.strip()) > 191:
        raise HTTPException(422, '用户名称最长 191 字')
    with AssetLibrary()._transaction() as cursor:
        cursor.execute(f'SELECT id FROM {table} WHERE id=%s FOR UPDATE', (identifier,))
        if cursor.fetchone() is None:
            raise HTTPException(404, '资源不存在')
        if payload.action == 'rename':
            field = 'name' if resource == 'assets' else 'nickname'
            cursor.execute(f'SELECT {field} FROM {table} WHERE id=%s', (identifier,))
            before = cursor.fetchone()
            after = {field: payload.name.strip()}
            cursor.execute(f'UPDATE {table} SET {field}=%s,updated_at=CURRENT_TIMESTAMP(3) WHERE id=%s', (payload.name.strip(),identifier))
        elif resource == 'assets':
            cursor.execute('SELECT status FROM assets WHERE id=%s', (identifier,))
            before = cursor.fetchone()
            if before['status'] == 'DELETED':
                raise HTTPException(422, '已删除素材不能通过停用操作恢复')
            after = {'status': 'BLOCKED' if payload.action == 'block' else 'ACTIVE'}
            cursor.execute('UPDATE assets SET status=%s WHERE id=%s', (after['status'],identifier))
        else:
            cursor.execute('SELECT blocked FROM platform_resource_controls WHERE resource_type=%s AND resource_id=%s FOR UPDATE',(kind,identifier))
            before = cursor.fetchone() or {'blocked': 0}
            after = {'blocked': int(payload.action == 'block')}
            cursor.execute('INSERT INTO platform_resource_controls (resource_type,resource_id,blocked) VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE blocked=VALUES(blocked)',(kind,identifier,after['blocked']))
        cursor.execute('INSERT INTO platform_admin_audit (id,actor_user_id,resource_type,resource_id,action,before_json,after_json) VALUES (%s,%s,%s,%s,%s,%s,%s)',(uuid.uuid4().hex,actor['id'],kind,identifier,payload.action,json.dumps(before),json.dumps(after)))
    return {'updated': True}
