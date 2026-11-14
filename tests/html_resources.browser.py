"""Local browser acceptance with a fake plaza service; never uses a real database."""
import io
import os
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


FRONTEND_URL = os.environ.get('HTML_RESOURCES_TEST_URL', 'http://127.0.0.1:18422').rstrip('/')


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
        def update_details(payload):
            publications[payload['jobId']].update(payload)
            return {'updated': True}
        resources.update_work_details = update_details
        resources.unpublish_work = lambda *args: {'published': False}
        platform_admin.ecosystem_change = lambda actor, identifier, owner, action, operation: operation()
        def update_cover(owner, identifier, url):
            publications[identifier]['coverUrl'] = url
            return {'updated': True}
        teacher_ecosystem.update_work_cover = update_cover
        app = FastAPI()
        app.include_router(resources.router)
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8019, log_level='error'))
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
                game_id = 'b' * 32
                game = {'id': game_id, 'name': '牛顿游戏课堂', 'owner_user_id': 'game-author', 'owner_email': 'teacher@example.com', 'status': 'SUCCEEDED', 'blocked': False, 'created_at': '2026-11-01T00:00:00'}
                game_publication = {'published': True, 'work': {'title': game['name'], 'featured': False}}
                def games_route(route):
                    from urllib.parse import parse_qs, urlsplit
                    query = parse_qs(urlsplit(route.request.url).query).get('search',[''])[0]
                    matches = not query or query in game['name'] or query in game['owner_email']
                    route.fulfill(json={'items':[dict(game)] if matches else [], 'total':1 if matches else 0, 'total_pages':1})
                def game_route(route):
                    if route.request.method == 'PATCH':
                        game['blocked'] = route.request.post_data_json['action'] == 'block'
                        route.fulfill(json={'ok':True})
                    else:
                        route.fulfill(json={'game':{**game,'source_material':'课堂主题：牛顿运动','options':{},'progress_percent':100,'draft_revision':1,'published_revision':1,'build_state':'ready','updated_at':game['created_at'],'scene_count':2,'image_count':1,'can_preview':True}})
                def publication_route(route):
                    if route.request.method == 'PATCH':
                        game_publication['work']['featured'] = route.request.post_data_json['featured']
                    route.fulfill(json=game_publication)
                page.route('**/api/forge/admin/games?*', games_route)
                page.route('**/api/forge/admin/games/'+game_id, game_route)
                page.route('**/api/forge/admin/games/'+game_id+'/ecosystem-publication', publication_route)
                page.goto(FRONTEND_URL + '/admin/', timeout=90000)
                page.wait_for_load_state('networkidle')
                page.get_by_role('tab', name='教学资源', exact=True).click()
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
                expect(page.get_by_role('button', name='重新生成封面', exact=True)).to_have_count(0)
                expect(page.get_by_role('button', name='替换封面', exact=True)).to_have_count(0)
                expect(page.get_by_role('button', name='修改标签', exact=True)).to_have_count(0)
                page.get_by_role('row').filter(has=page.get_by_role('button',name='编辑资源：行星公转实验室',exact=True)).get_by_role('button', name='设为精选', exact=True).click()
                expect(page.get_by_role('row').filter(has=page.get_by_role('button',name='编辑资源：行星公转实验室',exact=True)).get_by_role('button', name='取消精选', exact=True)).to_be_visible()
                page.get_by_role('button', name='编辑资源：行星公转实验室', exact=True).click()
                dialog = page.get_by_role('dialog')
                expect(dialog.get_by_role('heading', name='编辑课堂资源')).to_be_visible()
                import io as cover_io
                from PIL import Image
                cover_data = cover_io.BytesIO(); Image.new('RGB', (640, 360), '#e1edf5').save(cover_data, 'PNG')
                dialog.locator('#edit-cover').set_input_files({'name':'cover.png', 'mimeType':'image/png', 'buffer':cover_data.getvalue()})
                dialog.get_by_label('资源标题', exact=False).fill('行星公转实验室 · 新版')
                dialog.locator('textarea').fill('更新后的课堂简介')
                dialog.get_by_role('button', name='历史', exact=True).click()
                dialog.get_by_label('添加自定义标签', exact=True).fill('课后拓展')
                dialog.get_by_label('添加自定义标签', exact=True).press('Enter')
                dialog.evaluate('(el)=>el.scrollTop=0')
                dialog.screenshot(path=str(screenshot / 'resource-editor.png'))
                page.set_viewport_size({'width':390,'height':844})
                expect(dialog.get_by_role('button', name='保存设置', exact=True)).to_be_visible()
                dialog.evaluate('(el)=>el.scrollTop=0')
                dialog.screenshot(path=str(screenshot / 'resource-editor-mobile.png'))
                assert dialog.evaluate('(el)=>el.scrollWidth <= el.clientWidth + 1'), dialog.evaluate('(el)=>({width:el.clientWidth,scroll:el.scrollWidth,children:Array.from(el.querySelectorAll("*")).filter(x=>x.getBoundingClientRect().right>el.getBoundingClientRect().right+1).map(x=>[x.tagName,x.className,x.getBoundingClientRect().width]).slice(0,12)})')
                dialog.get_by_role('button', name='保存设置', exact=True).click()
                expect(dialog).not_to_be_visible(timeout=15000)
                assert len(publications) == 1
                identifier = next(iter(publications))
                assert publications[identifier]['featured'] is True
                assert publications[identifier]['title'] == '行星公转实验室 · 新版'
                assert publications[identifier]['summary'] == '更新后的课堂简介'
                assert '历史' in publications[identifier]['tags']
                assert '课后拓展' in publications[identifier]['tags']
                assert publications[identifier]['coverUrl']
                game_row = page.get_by_role('row').filter(has=page.get_by_role('button',name='查看游戏：牛顿游戏课堂',exact=True))
                expect(game_row).to_be_visible()
                game_row.get_by_role('button',name='设为精选',exact=True).click()
                expect(game_row.get_by_role('button',name='取消精选',exact=True)).to_be_visible()
                assert game_publication['work']['featured'] is True
                page.get_by_role('button',name='查看游戏：牛顿游戏课堂',exact=True).click()
                expect(page.get_by_role('dialog').get_by_text('游戏详情',exact=True)).to_be_visible()
                page.get_by_role('button',name='关闭详情',exact=True).click()
                type_filters = page.get_by_role('group',name='教学资源类型',exact=True)
                type_filters.get_by_role('button',name='HTML资源',exact=True).click()
                expect(page.get_by_role('button',name='查看游戏：牛顿游戏课堂',exact=True)).to_have_count(0)
                type_filters.get_by_role('button',name='游戏',exact=True).click()
                expect(page.get_by_role('button',name='编辑资源：行星公转实验室 · 新版',exact=True)).to_have_count(0)
                expect(page.get_by_role('button',name='查看游戏：牛顿游戏课堂',exact=True)).to_be_visible()
                type_filters.get_by_role('button',name='全部',exact=True).click()
                expect(page.get_by_role('button',name='编辑资源：行星公转实验室 · 新版',exact=True)).to_be_visible()
                expect(page.get_by_role('button',name='查看游戏：牛顿游戏课堂',exact=True)).to_be_visible()
                game_row.get_by_role('button',name='下架',exact=True).click()
                confirm = page.get_by_role('alertdialog')
                expect(confirm).to_be_visible()
                confirm.get_by_role('button',name='确认',exact=True).click()
                expect(game_row.get_by_role('button',name='恢复',exact=True)).to_be_visible()
                assert game['blocked'] is True
                page.set_viewport_size({'width':1440,'height':1000})
                page.screenshot(path=str(screenshot / 'teaching-resources.png'), full_page=True)
                page.set_viewport_size({'width': 390, 'height': 844})
                page.evaluate('window.scrollTo(0, 0)')
                page.screenshot(path=str(screenshot / 'admin-mobile.png'), full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                player = browser.new_page()
                player.goto(f'{FRONTEND_URL}/resources-play/{identifier}/')
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
                page.get_by_role('row').filter(has=page.get_by_role('button',name='编辑资源：行星公转实验室 · 新版',exact=True)).get_by_role('button', name='下架', exact=True).click()
                expect(page.get_by_role('button', name='重试发布', exact=True)).to_be_visible()
                assert player.request.get(f'{FRONTEND_URL}/resources-play/{identifier}/').status == 404
                # Check mixed pagination against a known interleaved sequence.
                from datetime import datetime, timedelta
                from urllib.parse import parse_qs, urlsplit
                html_rows = [{'id':format(1000+i,'032x'),'created_at':(datetime(2026,1,1)+timedelta(minutes=i*2)).isoformat()+'Z','state':'published','classification':{'subject':['科学'],'curriculum':[],'stage':[],'grade':[],'custom':[]},'payload':{'title':f'HTML-{i:02}','subject':'科学','tags':[],'playUrl':'#'}} for i in range(23)]
                game_rows = [{'id':format(2000+i,'032x'),'name':f'Game-{i:02}','created_at':(datetime(2026,1,1)+timedelta(minutes=i*2+1)).isoformat(),'blocked':False,'status':'SUCCEEDED'} for i in range(45)]
                game_rows.reverse()
                def many_games(route):
                    args=parse_qs(urlsplit(route.request.url).query)
                    current=int(args.get('page',['1'])[0]);query=args.get('search',[''])[0]
                    values=[item for item in game_rows if query in item['name']]
                    route.fulfill(json={'items':values[(current-1)*20:current*20],'total':len(values),'total_pages':max(1,(len(values)+19)//20)})
                page.route('**/api/forge/admin/html-resources', lambda route: route.fulfill(json={'items':html_rows}))
                page.route('**/api/forge/admin/games?*', many_games)
                page.route('**/ecosystem-publication', lambda route: route.fulfill(json={'published':False}))
                page.get_by_role('button',name='刷新列表',exact=True).click()
                expected = sorted([(item['created_at'].rstrip('Z'),'编辑资源：'+item['payload']['title']) for item in html_rows]+[(item['created_at'],'查看游戏：'+item['name']) for item in game_rows],reverse=True)
                seen=[]
                for current in range(4):
                    names=[name for _,name in expected[current*20:(current+1)*20]]
                    expect(page.get_by_role('button',name=names[0],exact=True)).to_be_visible()
                    buttons=page.locator('tbody button[aria-label^="编辑资源："],tbody button[aria-label^="查看游戏："]')
                    actual=buttons.evaluate_all('(items)=>items.map(el=>el.getAttribute("aria-label"))')
                    assert actual==names,(current,actual,names)
                    seen.extend(actual)
                    if current<3:page.get_by_role('button',name='下一页',exact=True).click()
                assert len(seen)==68 and len(set(seen))==68
                page.get_by_role('button',name='上一页',exact=True).click()
                expect(page.get_by_role('button',name=expected[40][1],exact=True)).to_be_visible()
                page.get_by_role('searchbox',name='搜索教学资源',exact=True).fill('Game-44')
                page.get_by_role('button',name='搜索',exact=True).click()
                expect(page.get_by_role('button',name='查看游戏：Game-44',exact=True)).to_be_visible()
                expect(page.locator('tbody tr')).to_have_count(1)
                browser.close()
                print(json.dumps({'result': 'passed', 'screenshots': str(screenshot), 'publication_count': len(publications)}))
        finally:
            server.should_exit = True
            thread.join(timeout=5)


if __name__ == '__main__':
    main()
