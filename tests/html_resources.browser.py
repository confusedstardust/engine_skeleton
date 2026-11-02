"""Local browser acceptance with a fake plaza service; never uses a real database."""
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from fastapi import FastAPI
from playwright.sync_api import sync_playwright, expect
from webgal_backend import html_resources as resources, platform_admin, teacher_ecosystem


def main():
    with tempfile.TemporaryDirectory() as directory:
        resources.settings = SimpleNamespace(jobs_dir=Path(directory))
        resources.require_admin = lambda request: {'id': 'fixture-admin'}
        resources.ecosystem_change = lambda actor, identifier, owner, action, operation: operation()
        publications = {}

        def publish(payload):
            publications[payload['jobId']] = payload
            return {'published': True}

        resources.publish_work = publish
        resources.unpublish_work = lambda *args: {'published': False}
        platform_admin.ecosystem_change = lambda actor, identifier, owner, action, operation: operation()
        def update_cover(owner, identifier, url):
            publications[identifier]['coverUrl'] = url
            return {'updated': True}
        teacher_ecosystem.update_work_cover = update_cover
        app = FastAPI()
        app.include_router(resources.router)
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=18424, log_level='error'))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        for _ in range(100):
            if server.started:
                break
            time.sleep(.05)
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, channel="msedge")
                page = browser.new_page(viewport={'width': 1440, 'height': 1100})
                page.route('**/api/forge/admin/me', lambda route: route.fulfill(json={'admin': True}))
                page.route('**/api/forge/admin/dashboard*', lambda route: route.fulfill(status=503, json={'detail': 'fixture'}))
                page.route('**/api/account/**', lambda route: route.fulfill(status=401, json={'error': 'fixture'}))
                page.goto('http://127.0.0.1:18422/admin/', timeout=90000)
                page.wait_for_load_state('networkidle')
                page.get_by_role('tab', name='HTML资源', exact=True).click()
                expect(page.get_by_role('heading', name='把你的课堂创意带到广场')).to_be_visible()
                page.locator('input[name=title]').fill('行星公转实验室')
                page.locator('textarea[name=summary]').fill('调整速度，观察行星公转的规律。')
                page.get_by_role('button', name='科学', exact=True).click()
                page.get_by_role('button', name='地理', exact=True).click()
                page.get_by_label('添加自定义标签', exact=True).fill('合作探究')
                page.get_by_label('添加自定义标签', exact=True).press('Enter')
                page.get_by_role('button', name='中国大陆课程', exact=True).click()
                page.get_by_role('button', name='初中', exact=True).click()
                data = io.BytesIO()
                with zipfile.ZipFile(data, 'w') as archive:
                    archive.writestr('lesson/index.html', '<!doctype html><script>window.earlyStorage=localStorage.getItem("lesson");</script><html><head></head><body><h1>行星实验室</h1><script type="module" src="app.mjs"></script></body></html>')
                    archive.writestr('lesson/app.mjs', 'import {message} from "./message.mjs"; document.body.dataset.loaded=message; document.body.dataset.early=String(window.earlyStorage); document.body.dataset.previous=localStorage.getItem("lesson"); document.body.dataset.private=String(localStorage.getItem("platform-private")); localStorage.setItem("lesson", "saved"); sessionStorage.setItem("session", "saved"); try { parent.document.body.dataset.escaped="yes"; } catch { document.body.dataset.isolated="yes"; }')
                    archive.writestr('lesson/message.mjs', 'export const message="ready";')
                page.locator('#html-resource-file').set_input_files({'name': 'lesson.zip', 'mimeType': 'application/zip', 'buffer': data.getvalue()})
                screenshot = Path(__file__).resolve().parents[1] / 'reports/html-resources'
                screenshot.mkdir(parents=True, exist_ok=True)
                page.evaluate('window.scrollTo(0, 0)')
                page.screenshot(path=str(screenshot / 'admin-desktop.png'), full_page=True)
                page.get_by_role('button', name='上传并发布到广场', exact=True).click()
                expect(page.get_by_role('cell', name='已发布', exact=True)).to_be_visible()
                expect(page.get_by_role('img', name='行星公转实验室封面')).to_be_visible(timeout=40000)
                page.get_by_role('button', name='重新生成封面', exact=True).click()
                expect(page.get_by_role('img', name='行星公转实验室封面')).to_be_visible()
                page.get_by_role('button', name='替换封面', exact=True).click()
                cover_dialog = page.get_by_role('dialog')
                import io as cover_io
                from PIL import Image
                cover_data = cover_io.BytesIO(); Image.new('RGB', (640, 360), 'blue').save(cover_data, 'PNG')
                cover_dialog.get_by_label('选择封面图片').set_input_files({'name':'cover.png', 'mimeType':'image/png', 'buffer':cover_data.getvalue()})
                cover_dialog.get_by_role('button', name='保存封面', exact=True).click()
                expect(cover_dialog).not_to_be_visible()
                assert len(publications) == 1
                identifier = next(iter(publications))
                assert '地理' in publications[identifier]['tags']
                assert '合作探究' in publications[identifier]['tags']
                page.get_by_role('button', name='修改标签', exact=True).click()
                dialog = page.get_by_role('dialog')
                dialog.get_by_role('button', name='历史', exact=True).click()
                dialog.get_by_label('添加自定义标签', exact=True).fill('课后拓展')
                dialog.get_by_label('添加自定义标签', exact=True).press('Enter')
                page.screenshot(path=str(screenshot / 'edit-tags.png'), full_page=True)
                dialog.get_by_role('button', name='保存标签', exact=True).click()
                expect(dialog).not_to_be_visible()
                assert '历史' in publications[identifier]['tags']
                assert '课后拓展' in publications[identifier]['tags']
                page.set_viewport_size({'width': 390, 'height': 844})
                page.evaluate('window.scrollTo(0, 0)')
                page.screenshot(path=str(screenshot / 'admin-mobile.png'), full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                player = browser.new_page()
                player.goto(f'http://127.0.0.1:18422/resources-play/{identifier}/')
                frame = player.frame_locator('iframe')
                expect(frame.locator('body')).to_have_attribute('data-loaded', 'ready')
                expect(frame.locator('body')).to_have_attribute('data-isolated', 'yes')
                assert player.locator('body').get_attribute('data-escaped') is None
                expect(frame.locator('body')).to_have_attribute('data-previous', 'null')
                player.wait_for_function("id => localStorage.getItem('narrativeos-resource:' + id + ':localStorage') !== null", arg=identifier)
                player.evaluate('localStorage.setItem("platform-private", "secret")')
                player.reload()
                expect(player.frame_locator('iframe').locator('body')).to_have_attribute('data-previous', 'saved')
                expect(player.frame_locator('iframe').locator('body')).to_have_attribute('data-early', 'saved')
                assert player.evaluate('localStorage.getItem("lesson")') is None
                expect(player.frame_locator('iframe').locator('body')).to_have_attribute('data-private', 'null')
                player.screenshot(path=str(screenshot / 'player.png'), full_page=True)
                page.get_by_role('button', name='下架', exact=True).click()
                expect(page.get_by_role('cell', name='已下架', exact=True)).to_be_visible()
                assert player.request.get(f'http://127.0.0.1:18422/resources-play/{identifier}/').status == 404
                browser.close()
                print(json.dumps({'result': 'passed', 'screenshots': str(screenshot), 'publication_count': len(publications)}))
        finally:
            server.should_exit = True
            thread.join(timeout=5)


if __name__ == '__main__':
    main()
