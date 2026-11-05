"""Upload real ZIPs to an isolated backend and exercise the opaque sandbox."""
import argparse
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright, expect
from webgal_backend import html_resources as resources, html_resource_covers


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--packages', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        resources.settings = SimpleNamespace(jobs_dir=Path(directory))
        resources.require_admin = lambda request: {'id': 'fixture-admin'}
        resources.ecosystem_change = lambda actor, identifier, owner, action, operation: operation()
        resources.publish_work = lambda payload: {'published': True, 'work': payload}
        resources.unpublish_work = lambda *args: {'published': False}
        html_resource_covers.generate_cover = lambda *args, **kwargs: None
        import os
        os.environ['WEBGAL_FRONTEND_URL'] = 'http://127.0.0.1:18520'
        app = FastAPI(); app.include_router(resources.router)
        client = TestClient(app, headers={'X-Forge-Admin-Action': '1'})
        uploaded = {}
        for name in ['reward-studio', 'recitation', 'poetry-challenge', 'sound-meter']:
            archive = args.packages / f'{name}.zip'
            response = client.post('/admin/html-resources', data={'title': name, 'subject': '跨学科'}, files={'file': (archive.name, archive.read_bytes(), 'application/zip')})
            assert response.status_code == 200, response.text
            uploaded[name] = response.json()['id']
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=18520, log_level='error'))
        thread = threading.Thread(target=server.run, daemon=True); thread.start()
        while not server.started: time.sleep(.05)
        try:
            with sync_playwright() as p:
                import wave,math,struct
                audio_file=Path(directory)/'signal.wav'
                with wave.open(str(audio_file),'wb') as audio:
                    audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(48000)
                    audio.writeframes(b''.join(struct.pack('<h',int(3000*math.sin(2*math.pi*440*i/48000))) for i in range(48000*4)))
                browser = p.chromium.launch(channel='msedge', args=['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream','--use-file-for-fake-audio-capture='+str(audio_file)])
                context = browser.new_context(viewport={'width':1440,'height':1000}, accept_downloads=True)
                context.add_init_script("""window.__micRequests=0;if(navigator.mediaDevices){const original=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);navigator.mediaDevices.getUserMedia=(...args)=>{window.__micRequests++;return original(...args).then(stream=>{window.__micStream=stream;return stream})}}""")
                page = context.new_page(); errors=[]
                page.on('pageerror', lambda error: errors.append(str(error)))
                screenshots = Path('reports/standalone-tools'); screenshots.mkdir(parents=True, exist_ok=True)
                def open_tool(name):
                    page.goto(f'http://127.0.0.1:18520/resources-play/{uploaded[name]}/', wait_until='networkidle')
                    assert 'allow-same-origin' not in page.locator('iframe').get_attribute('sandbox')
                    return page.frame_locator('iframe')
                frame = open_tool('recitation')
                expect(frame.get_by_role('button', name='换一轮', exact=True)).to_be_visible()
                before=frame.locator('.recite-reading').inner_html()
                frame.get_by_role('button',name='换一轮',exact=True).click()
                assert before != frame.locator('.recite-reading').inner_html()
                frame.get_by_role('button',name='查看原文',exact=True).click()
                expect(frame.get_by_role('button',name='继续留白练习',exact=True)).to_be_visible()
                page.screenshot(path=str(screenshots/'recitation.png'),full_page=True)
                frame = open_tool('poetry-challenge')
                expect(frame.locator('.poetry-app')).to_be_visible()
                options=frame.locator('.poetry-answer-options button')
                if options.count():
                    options.first.click()
                    expect(frame.locator('.poetry-app')).to_be_visible()

                page.screenshot(path=str(screenshots/'poetry.png'),full_page=True)
                frame = open_tool('reward-studio')
                frame.get_by_label('学生姓名',exact=False).fill('安安\n小满')
                expect(frame.locator('.reward-print-page')).to_have_count(2)
                assert 'allow-modals' in page.locator('iframe').get_attribute('sandbox')
                with page.expect_download(timeout=20000) as download:
                    frame.get_by_role('button',name='下载本页 PNG',exact=True).click()
                image=download.value; target=screenshots/'reward.png';image.save_as(target)
                from PIL import Image
                with Image.open(target) as result: assert result.size==(3508,2480)
                page.screenshot(path=str(screenshots/'rewards.png'),full_page=True)
                page.emulate_media(media='print')
                expect(frame.locator('.rewards-app')).not_to_be_visible()
                expect(frame.locator('.reward-print-root')).to_be_visible()
                box=frame.locator('.reward-print-page').first.bounding_box()
                assert abs(box['width']-297/25.4*96)<1 and abs(box['height']-210/25.4*96)<1
                page.emulate_media(media='screen')
                # Directly serve the same sandboxed document to verify browser PDF pagination.
                print_page=context.new_page()
                print_page.goto(f'http://127.0.0.1:18520/resources-play/{uploaded["reward-studio"]}/files/index.html',wait_until='networkidle')
                print_page.get_by_label('学生姓名',exact=False).fill('安安\n小满')
                print_page.pdf(path=str(screenshots/'rewards-a4.pdf'),prefer_css_page_size=True)
                import fitz
                with fitz.open(screenshots/'rewards-a4.pdf') as pdf:
                    assert len(pdf)==2
                    assert abs(pdf[0].rect.width-841.89)<2 and abs(pdf[0].rect.height-595.28)<2
                print_page.close()

                # A malicious SVG is rejected by the host renderer.
                bad_svg=frame.locator('body').evaluate("""()=>new Promise(resolve=>{const id='unsafe-svg-check';const receive=event=>{if(event.data?.type==='nos-resource-capability-result'&&event.data.id===id){removeEventListener('message',receive);resolve(event.data)}};addEventListener('message',receive);parent.postMessage({type:'nos-resource-capability',id,op:'png',width:100,height:100,svg:'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'},'*')})""")
                assert bad_svg['ok'] is False
                frame = open_tool('sound-meter')
                frame.get_by_role('button',name='开始监听',exact=True).click()
                consent=page.get_by_role('button',name='允许本资源使用麦克风（仅本机音量分析）',exact=True)
                expect(consent).to_be_visible()
                assert page.evaluate('window.__micRequests')==0
                consent.click()
                expect(page.get_by_role('button',name='停止麦克风',exact=True)).to_be_visible(timeout=15000)
                page.wait_for_timeout(1800)
                assert frame.locator('.sound-gauge').evaluate('(el)=>Array.from(el.querySelectorAll("*")).some(node=>/^-[0-9]+\\.[0-9]$/.test(node.textContent.trim())&&Number(node.textContent.trim())>-80)')
                assert page.evaluate('window.__micRequests')==1
                page.screenshot(path=str(screenshots/'microphone.png'),full_page=True)
                frame.get_by_role('button',name='结束监听',exact=True).click()
                expect(page.get_by_role('button',name='停止麦克风',exact=True)).not_to_be_visible()
                assert page.evaluate('window.__micStream.getTracks().every(track=>track.readyState==="ended")')
                # Ordinary HTML cannot request a microphone through the host.
                frame=open_tool('recitation')
                assert 'allow-modals' not in page.locator('iframe').get_attribute('sandbox')
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                identifier=uploaded['recitation']
                assert client.delete(f'/admin/html-resources/{identifier}/publication').status_code==200
                assert client.get(f'/resources-play/{identifier}/').status_code==404
                assert client.post(f'/admin/html-resources/{identifier}/publication').status_code==200
                assert client.get(f'/resources-play/{identifier}/').status_code==200
                assert not errors, errors
                browser.close()
                print(json.dumps({'result':'passed','tools':list(uploaded),'checks':['upload','recitation','PNG export','microphone consent + real browser audio path with synthetic input','archive/republish','opaque sandbox'],'screenshots':str(screenshots)}))
        finally:
            server.should_exit=True;thread.join(timeout=5)


if __name__ == '__main__': main()
