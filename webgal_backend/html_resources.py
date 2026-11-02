"""Admin-authored static teaching resources, published through the existing plaza bridge."""
from __future__ import annotations

import html
import io
import mimetypes
import os
import re
import shutil
import stat
import uuid
import zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from .config import settings
from .platform_admin import require_admin, require_action_header, ecosystem_change
from .storage import read_json, write_json
from .teacher_ecosystem import publish_work, unpublish_work

router = APIRouter(tags=['html-resources'])
MAX_UPLOAD = 30 * 1024 * 1024
MAX_EXPANDED = 120 * 1024 * 1024
TAXONOMY = {
    'curriculum': ['中国大陆课程', 'IB', 'Cambridge', 'AP', '通用拓展'],
    'stage': ['学前', '小学', '初中', '高中', '高等教育', '成人学习'],
    'subject': ['语文', '数学', '英语', '科学', '物理', '化学', '生物', '历史', '地理', '道德与法治', '思想政治', '信息科技', '通用技术', '音乐', '美术', '体育与健康', '劳动', '心理健康', '跨学科'],
    'grade': ['小班', '中班', '大班', '一年级', '二年级', '三年级', '四年级', '五年级', '六年级', '初一', '初二', '初三', '高一', '高二', '高三'],
}
EXTENSIONS = {'.html', '.htm', '.css', '.js', '.mjs', '.json', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.ico', '.mp3', '.wav', '.ogg', '.m4a', '.mp4', '.webm', '.woff', '.woff2', '.ttf', '.otf', '.wasm', '.txt', '.glb', '.gltf', '.bin', '.pdf'}


def resource_root():
    return settings.jobs_dir / '.html-resources'


def get_resource(identifier):
    if not re.fullmatch(r'[a-f0-9]{32}', identifier):
        raise HTTPException(404, '资源不存在')
    root = resource_root() / identifier
    try:
        return root, read_json(root / 'metadata.json')
    except FileNotFoundError:
        raise HTTPException(404, '资源不存在')


def safe_path(value):
    path = PurePosixPath(value)
    if not value or '\\' in value or ':' in value or path.is_absolute() or any(p in ('..', '.') or p.startswith('.') for p in value.split('/')):
        raise HTTPException(422, '资源包包含不安全路径')
    return path


def extract_package(data: bytes, filename: str, destination: Path, entry: str):
    destination.mkdir(parents=True)
    if filename.lower().endswith(('.html', '.htm')):
        (destination / 'index.html').write_bytes(data)
        return 'index.html'
    if not filename.lower().endswith('.zip'):
        raise HTTPException(422, '请选择 HTML 或 ZIP 文件')
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = [m for m in archive.infolist() if not m.is_dir() and not m.filename.startswith('__MACOSX/')]
            if len(members) > 2000 or sum(m.file_size for m in members) > MAX_EXPANDED:
                raise HTTPException(422, '资源包最多 2000 个文件，解压后不超过 120 MB')
            names = set()
            for member in members:
                path = safe_path(member.filename)
                if stat.S_ISLNK(member.external_attr >> 16) or member.flag_bits & 1:
                    raise HTTPException(422, '不支持链接或加密文件')
                if path.suffix.lower() not in EXTENSIONS or str(path).casefold() in names:
                    raise HTTPException(422, '资源包包含不支持或重名的文件')
                names.add(str(path).casefold())
                target = destination.joinpath(*path.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open('wb') as output:
                    shutil.copyfileobj(source, output)
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
        raise HTTPException(422, 'ZIP 文件损坏或压缩方式不受支持') from exc
    if entry:
        chosen = str(safe_path(entry))
    elif (destination / 'index.html').is_file():
        chosen = 'index.html'
    else:
        candidates = [p for p in destination.rglob('*') if p.is_file() and p.suffix.lower() in ('.html', '.htm')]
        indexes = [p for p in candidates if p.name.lower() == 'index.html']
        if len(indexes) == 1:
            chosen = indexes[0].relative_to(destination).as_posix()
        elif len(candidates) == 1:
            chosen = candidates[0].relative_to(destination).as_posix()
        else:
            raise HTTPException(422, '无法确定入口，请填写 ZIP 内的 HTML 入口路径')
    if Path(chosen).suffix.lower() not in ('.html', '.htm') or not (destination / chosen).is_file():
        raise HTTPException(422, 'HTML 入口不存在')
    return chosen


@contextmanager
def publication_lock(root):
    # A separate inode survives atomic metadata replacement and coordinates all server workers.
    with (root / 'publication.lock').open('a+b') as lock:
        lock.seek(0, os.SEEK_END)
        if lock.tell() == 0:
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise HTTPException(409, '资源正在发布或下架，请稍后刷新重试') from exc
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == 'nt':
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def change_publication(actor, identifier, publish):
    root, _ = get_resource(identifier)
    with publication_lock(root):
        # Read after locking: another operation may have just changed the state.
        return _change_publication(actor, identifier, root, publish)


def _change_publication(actor, identifier, root, publish):
    metadata = read_json(root / 'metadata.json')
    payload = metadata['payload']
    # Keep files available on an uncertain remote outcome so a successful remote write never yields a dead link.
    metadata['state'] = 'publishing' if publish else metadata['state']
    write_json(root / 'metadata.json', metadata)
    result = ecosystem_change(actor, identifier, {'id': payload['ownerUserId']},
                              'HTML_RESOURCE_PUBLISH' if publish else 'HTML_RESOURCE_UNPUBLISH',
                              lambda: publish_work(payload) if publish else unpublish_work(payload['ownerUserId'], identifier))
    metadata['state'] = 'published' if result.get('published') else 'archived'
    write_json(root / 'metadata.json', metadata)
    return {**metadata, **result}


@router.get('/admin/html-resources/taxonomy')
def taxonomy(request: Request):
    require_admin(request)
    return TAXONOMY


@router.get('/admin/html-resources')
def resources(request: Request):
    require_admin(request)
    items = [read_json(p) for p in resource_root().glob('*/metadata.json')]
    return {'items': sorted(items, key=lambda m: m['created_at'], reverse=True)}


@router.post('/admin/html-resources')
def upload_resource(request: Request, file: UploadFile = File(...), title: str = Form(...),
                    subject: str = Form(...), summary: str = Form(''), curriculum: str = Form(''),
                    stage: str = Form(''), grade: str = Form(''), entry: str = Form('')):
    actor = require_admin(request)
    require_action_header(request)
    if not title.strip() or len(title.strip()) > 160 or len(summary) > 2000:
        raise HTTPException(422, '标题必填且不超过 160 字，简介不超过 2000 字')
    for key, value in [('subject', subject), ('curriculum', curriculum), ('stage', stage), ('grade', grade)]:
        if (key == 'subject' or value) and value not in TAXONOMY[key]:
            raise HTTPException(422, '请选择有效的分类标签')
    grade_stages = dict(zip(TAXONOMY['grade'], ['学前'] * 3 + ['小学'] * 6 + ['初中'] * 3 + ['高中'] * 3))
    if stage and grade and grade_stages[grade] != stage:
        raise HTTPException(422, '所选年级与学段不一致，请调整后上传')
    data = file.file.read(MAX_UPLOAD + 1)
    if not data or len(data) > MAX_UPLOAD:
        raise HTTPException(413, '文件不能为空且不能超过 30 MB')
    identifier = uuid.uuid4().hex
    root = resource_root() / identifier
    try:
        chosen = extract_package(data, file.filename or '', root / 'files', entry.strip())
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise
    from .storage import utc_now
    base = os.getenv('WEBGAL_FRONTEND_URL', 'http://127.0.0.1:3001').rstrip('/')
    payload = {'ownerUserId': actor['id'], 'jobId': identifier, 'title': title.strip(),
               # Existing plaza stage filters read grade, including resources without a specific year.
               'summary': summary.strip() or None, 'subject': subject, 'grade': grade or stage or None,
               'tags': [v for v in (curriculum, stage, 'HTML互动资源') if v],
               'playUrl': f'{base}/resources-play/{identifier}/', 'coverUrl': None, 'quizUrl': None}
    metadata = {'id': identifier, 'payload': payload, 'entry': chosen, 'state': 'saved',
                'created_at': utc_now(), 'classification': {'curriculum': curriculum, 'stage': stage, 'grade': grade, 'subject': subject}}
    write_json(root / 'metadata.json', metadata)
    try:
        return change_publication(actor, identifier, True)
    except HTTPException as exc:
        raise HTTPException(exc.status_code, f'文件已保存（{identifier}），发布状态待确认；请在资源列表重试发布。{exc.detail}') from exc


@router.post('/admin/html-resources/{identifier}/publication')
def publish_resource(identifier: str, request: Request):
    actor = require_admin(request)
    require_action_header(request)
    return change_publication(actor, identifier, True)


@router.delete('/admin/html-resources/{identifier}/publication')
def archive_resource(identifier: str, request: Request):
    actor = require_admin(request)
    require_action_header(request)
    return change_publication(actor, identifier, False)


def public_resource(identifier):
    root, metadata = get_resource(identifier)
    if metadata['state'] not in ('publishing', 'published'):
        raise HTTPException(404, '资源未发布')
    return root, metadata


@router.get('/resources-play/{identifier}', response_class=HTMLResponse, include_in_schema=False)
@router.get('/resources-play/{identifier}/', response_class=HTMLResponse)
def player(identifier: str):
    _, metadata = public_resource(identifier)
    title = html.escape(metadata['payload']['title'])
    # Next rewrites may strip the trailing slash. Anchor files to the configured deployment prefix
    # so both player URLs resolve the same assets, including when served under a basePath.
    prefix = urlsplit(os.getenv('WEBGAL_FRONTEND_URL', '')).path.rstrip('/')
    source = html.escape(f"{prefix}/resources-play/{identifier}/files/" + quote(metadata['entry'], safe='/'), quote=True)
    return HTMLResponse(f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} · NarrativeOS</title><style>body{{margin:0;background:#f5f0e5;color:#412e26;font-family:system-ui}}header{{height:48px;display:flex;align-items:center;padding:0 20px;border-bottom:1px solid #d8cbb6;gap:16px}}strong{{color:#a23146}}iframe{{display:block;border:0;width:100%;height:calc(100dvh - 49px);background:white}}</style><header><strong>NarrativeOS</strong><span>{title}</span></header><iframe title="{title}" src="{source}" sandbox="allow-scripts allow-downloads" allow="fullscreen" referrerpolicy="no-referrer"></iframe></html>''', headers={
        'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; frame-src 'self'; frame-ancestors 'self'",
        'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store'})


@router.get('/resources-play/{identifier}/files/{file_path:path}')
def resource_file(identifier: str, file_path: str):
    root, _ = public_resource(identifier)
    path = safe_path(file_path)
    target = (root / 'files').joinpath(*path.parts)
    if not target.is_file():
        raise HTTPException(404, '资源文件不存在')
    mime = {'.mjs': 'text/javascript', '.js': 'text/javascript', '.wasm': 'application/wasm'}.get(target.suffix.lower()) or mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
    return FileResponse(target, media_type=mime, headers={
        'Content-Security-Policy': "sandbox allow-scripts allow-downloads; default-src 'self' https: data: blob:; script-src 'self' https: 'unsafe-inline' 'unsafe-eval' blob:; style-src 'self' https: 'unsafe-inline'; frame-ancestors 'self'; object-src 'none'",
        'Access-Control-Allow-Origin': '*', 'X-Content-Type-Options': 'nosniff',
        'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})
