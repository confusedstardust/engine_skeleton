"""Bounded, credential-free HTML screenshots and resource cover persistence."""
from __future__ import annotations

import io
import ipaddress
import json
import mimetypes
import os
import socket
import threading
import time
import uuid
import warnings
from http.client import HTTPConnection, HTTPSConnection
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit, quote

from PIL import Image, ImageOps

_browser_gate = threading.Semaphore(1)
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def normalized_image(data: bytes) -> bytes:
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError('封面不能为空且不能超过 5 MB')
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in ('JPEG', 'PNG', 'WEBP') or image.width * image.height > 36_000_000:
                raise ValueError('请选择不超过 3600 万像素的 PNG、JPEG 或 WebP 图片')
            image.draft('RGB', (2560, 1440))
            image.load()
            image = ImageOps.exif_transpose(image)
            image.thumbnail((2560, 1440), Image.Resampling.LANCZOS)
            image = image.convert('RGBA')
            background = Image.new('RGBA', image.size, '#faf7f2')
            background.alpha_composite(image)
            image = ImageOps.fit(background.convert('RGB'), (1280, 720), method=Image.Resampling.LANCZOS)
            result = io.BytesIO()
            image.save(result, 'WEBP', quality=85)
            return result.getvalue()


def public_asset(url: str, remaining: int) -> tuple[int, bytes, str]:
    """Fetch public HTTP assets with pinned DNS, bounded redirects, and no cookies."""
    for _ in range(5):
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password:
            raise ValueError('不支持的外部资源地址')
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        if port not in (80, 443):
            raise ValueError('外部资源端口受限')
        addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
            raise ValueError('封面不访问内网地址')
        pinned = min(addresses, key=lambda row: row[0] != socket.AF_INET)[4][0]
        connection = (HTTPSConnection if parsed.scheme == 'https' else HTTPConnection)(parsed.hostname, port, timeout=4)
        # HTTPS retains the original hostname for SNI/certificate verification, but TCP cannot re-resolve it.
        connection._create_connection = lambda address, timeout, source_address=None: socket.create_connection((pinned, port), timeout, source_address)
        try:
            connection.request('GET', parsed.path + ('?' + parsed.query if parsed.query else '') or '/',
                               headers={'Accept-Encoding': 'identity', 'User-Agent': 'NarrativeOS-Cover/1'})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                url = urljoin(url, response.getheader('Location', ''))
                continue
            data = response.read(min(5 * 1024 * 1024, remaining) + 1)
            if len(data) > min(5 * 1024 * 1024, remaining):
                raise ValueError('外部资源超过截图大小限制')
            return response.status, data, response.getheader('Content-Type', 'application/octet-stream')
        finally:
            connection.close()
    raise ValueError('外部资源重定向过多')


def capture(root: Path, entry: str) -> tuple[bytes, int]:
    from playwright.sync_api import sync_playwright
    from .html_resources import sandbox_document
    failed = 0
    budget = 30 * 1024 * 1024
    requests = 0
    with _browser_gate, sync_playwright() as playwright:
        options = {'headless': True}
        if os.name == 'nt':
            options['channel'] = 'msedge'
        browser = playwright.chromium.launch(**options)
        deadline = time.monotonic() + 30
        try:
            context = browser.new_context(viewport={'width': 1280, 'height': 720}, device_scale_factor=1,
                                          reduced_motion='reduce', service_workers='block', accept_downloads=False)
            page = context.new_page()
            page.set_default_timeout(5000)
            def route_request(route):
                nonlocal budget, failed, requests
                parsed = urlsplit(route.request.url)
                try:
                    requests += 1
                    if requests > 100 or time.monotonic() > deadline:
                        raise ValueError('截图资源加载达到限额')
                    if route.request.method != 'GET':
                        raise ValueError('截图不提交表单')
                    if parsed.hostname == 'resource.invalid':
                        target = (root / unquote(parsed.path).lstrip('/')).resolve()
                        if not target.is_relative_to(root.resolve()) or not target.is_file():
                            raise ValueError('附件不存在')
                        if target.stat().st_size > budget:
                            raise ValueError('截图附件超过大小限制')
                        data = target.read_bytes()
                        budget -= len(data)
                        mime = mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
                        headers = {'Access-Control-Allow-Origin': '*'}
                        if target.suffix.lower() in ('.html', '.htm'):
                            data = sandbox_document(data)
                            mime = 'text/html; charset=utf-8'
                            headers['Content-Security-Policy'] = "sandbox allow-scripts; object-src 'none'"
                        elif target.suffix.lower() in ('.js', '.mjs') or target.name.endswith('.js.下载'):
                            mime = 'text/javascript'
                        route.fulfill(body=data, content_type=mime, headers=headers)
                    else:
                        status, data, mime = public_asset(route.request.url, budget)
                        budget -= len(data)
                        route.fulfill(status=status, body=data, content_type=mime, headers={'Access-Control-Allow-Origin': '*'})
                except Exception:
                    failed += 1
                    route.abort()
            context.route('**/*', route_request)
            context.route_web_socket('**/*', lambda ws: ws.close())
            page.on('dialog', lambda dialog: dialog.dismiss())
            page.goto('https://resource.invalid/' + quote(entry, safe='/'), wait_until='domcontentloaded', timeout=25000)
            page.wait_for_timeout(1200)
            try:
                page.evaluate('() => Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 2000))])')
            except Exception:
                pass
            data = page.screenshot(type='png', full_page=False, timeout=8000)
            return normalized_image(data), failed
        finally:
            browser.close()


def save_cover(actor, identifier, data: bytes, *, revision=None, source='manual', failed_assets=0):
    from .html_resources import get_resource, publication_lock
    from .storage import read_json, write_json, utc_now
    root, _ = get_resource(identifier)
    with publication_lock(root):
        metadata = read_json(root / 'metadata.json')
        if revision is not None and metadata.get('cover_revision') != revision:
            return metadata  # A newer upload/regeneration wins.
        name = uuid.uuid4().hex + '.webp'
        directory = root / 'covers'
        directory.mkdir(exist_ok=True)
        (directory / name).write_bytes(data)
        base = os.getenv('WEBGAL_FRONTEND_URL', 'http://127.0.0.1:3001').rstrip('/')
        metadata['payload']['coverUrl'] = f'{base}/resources-play/{identifier}/cover/{name}'
        metadata.update(cover_status='ready', cover_error='', cover_source=source, cover_updated_at=utc_now(),
                        cover_failed_assets=failed_assets, cover_revision=uuid.uuid4().hex)
        write_json(root / 'metadata.json', metadata)
        if metadata['state'] in ('published', 'publishing'):
            try:
                return sync_cover_locked(actor, identifier, root, metadata)
            except Exception as exc:
                metadata = read_json(root / 'metadata.json')
                metadata.update(cover_status='sync_failed', cover_error='封面已保存，广场同步失败，请重试发布：' + str(getattr(exc, 'detail', exc))[:200])
                write_json(root / 'metadata.json', metadata)
                return metadata
        return metadata


def sync_cover_locked(actor, identifier, root, metadata):
    from .platform_admin import ecosystem_change
    from .teacher_ecosystem import update_work_cover
    from .storage import write_json
    payload = metadata['payload']
    result = ecosystem_change(actor, identifier, {'id': payload['ownerUserId']}, 'HTML_RESOURCE_COVER',
                              lambda: update_work_cover(payload['ownerUserId'], identifier, payload['coverUrl']))
    if not result.get('updated'):
        raise ValueError('广场未确认封面更新')
    metadata.update(cover_status='ready', cover_error='')
    write_json(root / 'metadata.json', metadata)
    return metadata


def sync_cover(actor, identifier):
    from .html_resources import get_resource, publication_lock
    from .storage import read_json
    root, _ = get_resource(identifier)
    with publication_lock(root):
        metadata = read_json(root / 'metadata.json')
        if not metadata['payload'].get('coverUrl'):
            raise ValueError('尚无可同步的封面')
        if metadata['state'] in ('published', 'publishing'):
            return sync_cover_locked(actor, identifier, root, metadata)
        return metadata


def generate_cover(actor, identifier, *, only_missing=False, expected_revision=None):
    from .html_resources import get_resource, publication_lock
    from .storage import read_json, write_json
    root, metadata = get_resource(identifier)
    revision = expected_revision or uuid.uuid4().hex
    with publication_lock(root):
        metadata = read_json(root / 'metadata.json')
        if expected_revision is not None and metadata.get('cover_revision') != expected_revision:
            return metadata
        if only_missing and metadata['payload'].get('coverUrl'):
            return metadata
        metadata.update(cover_status='generating', cover_error='', cover_revision=revision)
        write_json(root / 'metadata.json', metadata)
    try:
        data, failed = capture(root / 'files', metadata['entry'])
        return save_cover(actor, identifier, data, revision=revision, source='automatic', failed_assets=failed)
    except Exception as exc:
        with publication_lock(root):
            metadata = read_json(root / 'metadata.json')
            if metadata.get('cover_revision') == revision:
                metadata.update(cover_status='failed', cover_error=str(exc)[:300])
                write_json(root / 'metadata.json', metadata)
        return metadata


def backfill(*, stop_event=None):
    from .html_resources import resource_root
    from .storage import read_json
    results = []
    for path in sorted(resource_root().glob('*/metadata.json')):
        if stop_event is not None and stop_event.is_set():
            break
        record = read_json(path)
        if record['state'] not in ('published', 'publishing'):
            continue
        if record.get('cover_status') == 'sync_failed':
            try:
                result = sync_cover({'id': record['payload']['ownerUserId']}, record['id'])
            except Exception as exc:
                result = {'cover_status': 'sync_failed', 'cover_error': str(exc)[:200]}
            results.append({'id': record['id'], 'status': result.get('cover_status')})
            print(json.dumps(results[-1], ensure_ascii=False), flush=True)
            continue
        if record['payload'].get('coverUrl'):
            continue
        try:
            result = generate_cover({'id': record['payload']['ownerUserId']}, record['id'], only_missing=True)
        except Exception as exc:
            result = {'cover_status': 'failed', 'cover_error': str(exc)[:200]}
        results.append({'id': record['id'], 'status': result.get('cover_status'), 'error': result.get('cover_error', '')})
        print(json.dumps(results[-1], ensure_ascii=False), flush=True)
    return results


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--backfill-missing', action='store_true', required=True)
    parser.parse_args()
    results = backfill()
    raise SystemExit(1 if any(row['status'] != 'ready' for row in results) else 0)
