"""Admin-authored static teaching resources, published through the existing plaza bridge."""
from __future__ import annotations

import html
import json
from html.parser import HTMLParser
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
from urllib.parse import quote, urlsplit, unquote

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field

from .config import settings
from .platform_admin import require_admin, require_action_header, ecosystem_change
from .storage import read_json, write_json
from .teacher_ecosystem import publish_work, unpublish_work, update_work_details

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


def tag_values(value):
    if isinstance(value, str):
        if value.lstrip().startswith('['):
            try:
                value = json.loads(value)
            except ValueError:
                raise HTTPException(422, '标签格式无效')
        else:
            value = [value] if value.strip() else []
    if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
        raise HTTPException(422, '标签必须为文字列表')
    result = list(dict.fromkeys(v.strip() for v in value if v.strip()))
    if len(result) > 30 or any(len(v) > 40 for v in result):
        raise HTTPException(422, '每组最多 30 个标签，每个标签不超过 40 字')
    return result


def classification_values(values):
    result = {key: tag_values(values.get(key, [])) for key in (*TAXONOMY, 'custom')}
    if not result['subject']:
        raise HTTPException(422, '请至少选择一个学科')
    tags = list(dict.fromkeys(v for group in result.values() for v in group))
    if len(tags) > 63:
        raise HTTPException(422, '分类与自定义标签合计最多 63 个')
    return result


def apply_classification(payload, values):
    return {**payload, 'subject': values['subject'][0],
            'grade': next(iter(values['grade'] or values['stage']), None),
            'tags': list(dict.fromkeys([v for group in values.values() for v in group] + ['HTML互动资源']))}


def editable_classification(metadata):
    original = metadata.get('classification', {})
    result = {key: tag_values(original.get(key, [])) for key in (*TAXONOMY, 'custom')}
    if not result['subject'] and metadata['payload'].get('subject'):
        result['subject'] = [metadata['payload']['subject']]
    return result


def resource_capabilities(files):
    manifest = files / 'narrativeos-resource.json'
    if not manifest.is_file():
        return []
    if manifest.stat().st_size > 16384:
        raise HTTPException(422, '资源能力声明过大')
    try:
        body = json.loads(manifest.read_text(encoding='utf-8'))
        values = body.get('capabilities', [])
        if not isinstance(values, list) or any(value not in ('print', 'png-export', 'microphone') for value in values):
            raise ValueError('invalid capabilities')
        return list(dict.fromkeys(values))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(422, '资源能力声明无效')


def resource_root():
    return settings.jobs_dir / '.html-resources'


class RequiredReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'img', 'audio', 'video', 'source', 'iframe') and attrs.get('src'):
            self.paths.append(attrs['src'])
        if tag == 'video' and attrs.get('poster'):
            self.paths.append(attrs['poster'])
        if tag == 'link' and 'stylesheet' in attrs.get('rel', '').split() and attrs.get('href'):
            self.paths.append(attrs['href'])


def validate_references(root, entry):
    parser = RequiredReferences()
    parser.feed((root / entry).read_text(encoding='utf-8-sig', errors='replace'))
    missing = []
    for value in parser.paths:
        url = urlsplit(value)
        if url.scheme or url.netloc or not url.path:
            continue
        target = (root / entry).parent / unquote(url.path)
        if not target.resolve().is_relative_to(root.resolve()) or not target.is_file():
            missing.append(unquote(url.path))
    if missing:
        raise HTTPException(422, '缺少页面引用的资源：' + '、'.join(dict.fromkeys(missing))[:600] + '。请将 HTML 与配套资源目录一起打包为 ZIP，保留目录结构。')


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
                if (path.suffix.lower() not in EXTENSIONS and not path.name.lower().endswith('.js.下载')) or str(path).casefold() in names:
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
    remote_tags = (result.get('work') or {}).get('tags')
    if publish and result.get('published') and isinstance(remote_tags, list) and set(remote_tags) != set(payload['tags']):
        raise HTTPException(409, '广场服务未保存完整标签，请更新门户服务后重试发布')
    metadata['state'] = 'published' if result.get('published') else 'archived'
    write_json(root / 'metadata.json', metadata)
    return {**metadata, **result}


@router.get('/admin/html-resources/taxonomy')
def taxonomy(request: Request):
    require_admin(request)
    vocabulary = {**{key: list(values) for key, values in TAXONOMY.items()}, 'custom': []}
    for path in resource_root().glob('*/metadata.json'):
        for key, values in editable_classification(read_json(path)).items():
            vocabulary[key] = list(dict.fromkeys(vocabulary[key] + values))
    return vocabulary


@router.get('/admin/html-resources')
def resources(request: Request):
    require_admin(request)
    items = [read_json(p) for p in resource_root().glob('*/metadata.json')]
    for item in items:
        item['classification'] = editable_classification(item)
    return {'items': sorted(items, key=lambda m: m['created_at'], reverse=True)}


@router.post('/admin/html-resources')
def upload_resource(request: Request, background_tasks: BackgroundTasks, file: UploadFile = File(...), title: str = Form(...),
                    subject: str = Form(...), summary: str = Form(''), curriculum: str = Form(''),
                    stage: str = Form(''), grade: str = Form(''), entry: str = Form(''), custom: str = Form('')):
    actor = require_admin(request)
    require_action_header(request)
    if not title.strip() or len(title.strip()) > 160 or len(summary) > 2000:
        raise HTTPException(422, '标题必填且不超过 160 字，简介不超过 2000 字')
    classification = classification_values(dict(subject=subject, curriculum=curriculum, stage=stage, grade=grade, custom=custom))
    data = file.file.read(MAX_UPLOAD + 1)
    if not data or len(data) > MAX_UPLOAD:
        raise HTTPException(413, '文件不能为空且不能超过 30 MB')
    identifier = uuid.uuid4().hex
    root = resource_root() / identifier
    try:
        chosen = extract_package(data, file.filename or '', root / 'files', entry.strip())
        validate_references(root / 'files', chosen)
        capabilities = resource_capabilities(root / 'files')
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise
    from .storage import utc_now
    base = os.getenv('WEBGAL_FRONTEND_URL', 'http://127.0.0.1:3001').rstrip('/')
    payload = {'ownerUserId': actor['id'], 'jobId': identifier, 'title': title.strip(),
               'summary': summary.strip() or None,
               'playUrl': f'{base}/resources-play/{identifier}/', 'coverUrl': None, 'quizUrl': None}
    payload = apply_classification(payload, classification)
    metadata = {'id': identifier, 'payload': payload, 'entry': chosen, 'state': 'saved',
                'created_at': utc_now(), 'classification': classification, 'capabilities': capabilities}
    write_json(root / 'metadata.json', metadata)
    try:
        result = change_publication(actor, identifier, True)
        request_cover(actor, identifier, background_tasks)
        return {**result, 'cover_status': 'pending'}
    except HTTPException as exc:
        raise HTTPException(exc.status_code, f'文件已保存（{identifier}），发布状态待确认；请在资源列表重试发布。{exc.detail}') from exc


def request_cover(actor, identifier, background_tasks):
    from .html_resource_covers import generate_cover
    root, _ = get_resource(identifier)
    revision = uuid.uuid4().hex
    with publication_lock(root):
        metadata = read_json(root / 'metadata.json')
        metadata.update(cover_status='pending', cover_error='', cover_revision=revision)
        write_json(root / 'metadata.json', metadata)
    background_tasks.add_task(generate_cover, actor, identifier, expected_revision=revision)


@router.post('/admin/html-resources/{identifier}/cover/generate', status_code=202)
def regenerate_cover(identifier: str, request: Request, background_tasks: BackgroundTasks):
    actor = require_admin(request)
    require_action_header(request)
    request_cover(actor, identifier, background_tasks)
    return {'id': identifier, 'cover_status': 'pending'}


@router.post('/admin/html-resources/{identifier}/cover')
def upload_cover(identifier: str, request: Request, file: UploadFile = File(...)):
    from .html_resource_covers import normalized_image, save_cover, MAX_IMAGE_BYTES
    from PIL import Image
    actor = require_admin(request)
    require_action_header(request)
    get_resource(identifier)
    try:
        data = normalized_image(file.file.read(MAX_IMAGE_BYTES + 1))
    except (ValueError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise HTTPException(422, '封面图片无效：' + str(exc)[:150]) from exc
    return save_cover(actor, identifier, data)


@router.post('/admin/html-resources/{identifier}/cover/sync')
def retry_cover_sync(identifier: str, request: Request):
    from .html_resource_covers import sync_cover
    actor = require_admin(request)
    require_action_header(request)
    return sync_cover(actor, identifier)


class ResourceTags(BaseModel):
    classification: dict[str, list[str]] = Field(default_factory=dict)


def sync_resource_details(actor, identifier, root, metadata):
    # Save desired metadata first, so an uncertain remote write can be retried.
    write_json(root / 'metadata.json', metadata)
    if metadata['state'] in ('published', 'publishing'):
        try:
            ecosystem_change(actor, identifier, {'id': metadata['payload']['ownerUserId']},
                             'HTML_RESOURCE_EDIT', lambda: update_work_details(metadata['payload']))
        except HTTPException as exc:
            metadata['metadata_sync_error'] = '修改已保存在后台，广场同步待重试'
            write_json(root / 'metadata.json', metadata)
            raise HTTPException(exc.status_code, metadata['metadata_sync_error'] + '；请再次保存。') from exc
    metadata.pop('metadata_sync_error', None)
    write_json(root / 'metadata.json', metadata)
    return metadata


@router.patch('/admin/html-resources/{identifier}')
def edit_resource(identifier: str, request: Request, title: str = Form(...), summary: str = Form(''),
                  classification: str = Form(...), featured: bool = Form(False),
                  entry: str = Form(''), file: UploadFile | None = File(None)):
    actor = require_admin(request)
    require_action_header(request)
    if not title.strip() or len(title.strip()) > 160 or len(summary) > 2000 or len(entry) > 500:
        raise HTTPException(422, '标题必填且不超过 160 字，简介不超过 2000 字，入口不超过 500 字')
    try:
        raw = json.loads(classification)
    except ValueError:
        raise HTTPException(422, '分类格式无效')
    if not isinstance(raw, dict):
        raise HTTPException(422, '分类格式无效')
    values = classification_values(raw)
    root, _ = get_resource(identifier)
    with publication_lock(root):
        metadata = read_json(root / 'metadata.json')
        files_dir = metadata.get('files_dir', 'files')
        chosen = entry.strip() or metadata['entry']
        if file is not None:
            data = file.file.read(MAX_UPLOAD + 1)
            if not data or len(data) > MAX_UPLOAD:
                raise HTTPException(413, '文件不能为空且不能超过 30 MB')
            files_dir = 'files-' + uuid.uuid4().hex
            try:
                chosen = extract_package(data, file.filename or '', root / files_dir, entry.strip())
                validate_references(root / files_dir, chosen)
                capabilities = resource_capabilities(root / files_dir)
            except Exception:
                shutil.rmtree(root / files_dir, ignore_errors=True)
                raise
        else:
            chosen = str(safe_path(chosen))
            if Path(chosen).suffix.lower() not in ('.html', '.htm') or not (root / files_dir / chosen).is_file():
                raise HTTPException(422, 'HTML 入口不存在')
            if chosen != metadata['entry']:
                validate_references(root / files_dir, chosen)
        metadata.update(classification=values, entry=chosen, files_dir=files_dir)
        if file is not None:
            metadata['capabilities'] = capabilities
            # Invalidate an in-flight screenshot of the previous package.
            metadata.update(cover_revision=uuid.uuid4().hex, cover_error='')
            if metadata.get('cover_status') in ('pending', 'generating'):
                metadata['cover_status'] = 'ready' if metadata['payload'].get('coverUrl') else 'idle'
        metadata['payload'] = apply_classification({**metadata['payload'], 'title': title.strip(),
                                                   'summary': summary.strip() or None, 'featured': featured}, values)
        return sync_resource_details(actor, identifier, root, metadata)


class ResourceFeatured(BaseModel):
    featured: bool


@router.patch('/admin/html-resources/{identifier}/featured')
def feature_resource(identifier: str, body: ResourceFeatured, request: Request):
    actor = require_admin(request)
    require_action_header(request)
    root, _ = get_resource(identifier)
    with publication_lock(root):
        metadata = read_json(root / 'metadata.json')
        metadata['payload']['featured'] = body.featured
        return sync_resource_details(actor, identifier, root, metadata)


@router.patch('/admin/html-resources/{identifier}/tags')
def edit_resource_tags(identifier: str, body: ResourceTags, request: Request):
    actor = require_admin(request)
    require_action_header(request)
    values = classification_values(body.classification)
    root, _ = get_resource(identifier)
    with publication_lock(root):
        metadata = read_json(root / 'metadata.json')
        metadata['classification'] = values
        metadata['payload'] = apply_classification(metadata['payload'], values)
        # Persist the desired update before the remote call so timeouts can be retried by ID.
        write_json(root / 'metadata.json', metadata)
        if metadata['state'] in ('published', 'publishing'):
            return _change_publication(actor, identifier, root, True)
        return metadata


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
    runtime = html.escape(f'{prefix}/resources-play/{identifier}/player.js', quote=True)
    capability_runtime = html.escape(f'{prefix}/resources-play/{identifier}/capabilities.js', quote=True)
    capabilities = metadata.get('capabilities', [])
    sandbox = 'allow-scripts allow-downloads' + (' allow-modals' if 'print' in capabilities else '')
    encoded_capabilities = html.escape(json.dumps(capabilities), quote=True)
    return HTMLResponse(f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} · NarrativeOS</title><style>body{{margin:0;background:#f5f0e5;color:#412e26;font-family:system-ui}}header{{height:48px;display:flex;align-items:center;padding:0 20px;border-bottom:1px solid #d8cbb6;gap:16px}}strong{{color:#a23146}}iframe{{display:block;border:0;width:100%;height:calc(100dvh - 49px);background:white}}</style><header><strong>NarrativeOS</strong><span>{title}</span></header><iframe title="{title}" data-resource="{identifier}" data-src="{source}" data-capabilities="{encoded_capabilities}" sandbox="{sandbox}" allow="fullscreen" referrerpolicy="no-referrer"></iframe><script src="{runtime}"></script><script src="{capability_runtime}"></script></html>''', headers={
        'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; script-src 'self'; img-src blob:; frame-src 'self'; frame-ancestors 'self'",
        'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store'})


@router.get('/resources-play/{identifier}/files/{file_path:path}')
def resource_file(identifier: str, file_path: str):
    root, metadata = public_resource(identifier)
    path = safe_path(file_path)
    target = (root / metadata.get('files_dir', 'files')).joinpath(*path.parts)
    if not target.is_file():
        raise HTTPException(404, '资源文件不存在')
    mime = {'.mjs': 'text/javascript', '.js': 'text/javascript', '.wasm': 'application/wasm'}.get(target.suffix.lower()) or mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
    sandbox = 'allow-scripts allow-downloads' + (' allow-modals' if 'print' in metadata.get('capabilities', []) else '')
    headers = {
        'Content-Security-Policy': f"sandbox {sandbox}; default-src 'self' https: data: blob:; script-src 'self' https: 'unsafe-inline' 'unsafe-eval' blob:; style-src 'self' https: 'unsafe-inline'; frame-ancestors 'self'; object-src 'none'",
        'Access-Control-Allow-Origin': '*', 'X-Content-Type-Options': 'nosniff',
        'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'}
    if target.suffix.lower() in ('.html', '.htm'):
        return Response(sandbox_document(target.read_bytes()), media_type='text/html', headers=headers)
    if target.name.lower().endswith('.js.下载'):
        mime = 'text/javascript'
    return FileResponse(target, media_type=mime, headers=headers)


def sandbox_document(content):
    bootstrap = b'<script>' + Path(__file__).with_name('resource_storage.js').read_bytes() + b'</script>'
    doctype = re.match(br'\s*(?:<!--.*?-->\s*)*<!doctype[^>]*>', content, re.I | re.S)
    position = doctype.end() if doctype else 0
    return content[:position] + bootstrap + content[position:]


@router.get('/resources-play/{identifier}/cover/{name}')
def cover_file(identifier: str, name: str):
    root, _ = public_resource(identifier)
    if not re.fullmatch(r'[a-f0-9]{32}\.webp', name) or not (root / 'covers' / name).is_file():
        raise HTTPException(404, '封面不存在')
    return FileResponse(root / 'covers' / name, media_type='image/webp',
                        headers={'Cache-Control': 'public, max-age=31536000, immutable', 'X-Content-Type-Options': 'nosniff'})


@router.get('/resources-play/{identifier}/player.js')
def player_runtime(identifier: str):
    public_resource(identifier)
    return FileResponse(Path(__file__).with_name('resource_player.js'), media_type='text/javascript',
                        headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})


@router.get('/resources-play/{identifier}/capabilities.js')
def capability_script(identifier: str):
    public_resource(identifier)
    return FileResponse(Path(__file__).with_name('resource_capabilities.js'), media_type='text/javascript',
                        headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
