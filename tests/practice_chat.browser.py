"""Run against a local Next dev server; API responses are mocked, no paid calls."""
import json
import os
import re
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

out = Path("reports/nar-agent")
out.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel=os.getenv("TEST_BROWSER_CHANNEL", "msedge"))
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    calls = []
    page.route("**/api/forge/auth/me", lambda route: route.fulfill(json={"id": "ui-test", "auth_type": "sso", "nickname": "测试教师"}))

    def answer(route):
        calls.append(route.request.post_data_json)
        route.fulfill(json={"id": "test-run", "output": "串联电路各处电流相同。" if len(calls) == 1 else "加入重置按钮。", "artifact_generated": False})

    page.route("**/api/forge/nar-agent/chat", answer)
    base = os.getenv("TEST_FRONTEND_URL", "http://127.0.0.1:3001")
    page.goto(base + "/", wait_until="networkidle", timeout=60000)
    page.locator(".router-start").click()
    page.locator(".scene-card").filter(has_text="讲练工具").click()
    page.wait_for_url(re.compile(r"/practice/?$"), timeout=30000)
    page.get_by_label("输入教学问题").fill("设计一个串联电路演示")
    page.get_by_role("button", name="发送 ↗").click()
    page.get_by_text("串联电路各处电流相同。", exact=True).wait_for()
    page.get_by_label("输入教学问题").fill("再加一个重置按钮")
    page.get_by_role("button", name="发送 ↗").click()
    page.get_by_text("加入重置按钮。", exact=True).wait_for()
    assert len(calls[1]["history"]) == 2
    page.screenshot(path=str(out / "practice-desktop.png"), full_page=True)
    page.get_by_role("button", name="＋ 开始新对话").click()
    page.get_by_role("heading", name=re.compile("你想让学生.*看懂什么")).wait_for()
    page.route("**/api/forge/nar-agent/chat", lambda route: route.fulfill(status=503, json={"detail": "讲练助手暂时无法连接，请稍后重试"}))
    page.get_by_label("输入教学问题").fill("测试失败保留输入")
    page.get_by_role("button", name="发送 ↗").click()
    page.locator('p[role="alert"]').wait_for()
    assert page.get_by_label("输入教学问题").input_value() == "测试失败保留输入"
    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(path=str(out / "practice-mobile.png"), full_page=True)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.route("**/api/forge/nar-agent/animations", lambda route: route.fulfill(status=202, json={"id": "a" * 32, "status": "RUNNING"}))
    page.route("**/api/forge/nar-agent/animations/" + "a" * 32, lambda route: route.fulfill(json={"id": "a" * 32, "status": "SUCCEEDED", "output": "点击开关观察灯泡。", "artifact_id": "b" * 32}))
    page.route("**/api/forge/nar-agent/artifacts/" + "b" * 32 + "/index.html", lambda route: route.fulfill(content_type="text/html", body='<html><body><svg width="100" height="80"><circle cx="40" cy="40" r="20" fill="gold"/></svg><button onclick="this.textContent=\'开关已打开\'">开关</button></body></html>'))
    page.get_by_label("输入教学问题").fill("生成电路动画")
    page.get_by_role("button", name="制作动画", exact=True).click()
    frame = page.frame_locator('iframe[title="教学动画"]')
    frame.get_by_role("button", name="开关", exact=True).click()
    frame.get_by_role("button", name="开关已打开", exact=True).wait_for()
    assert page.locator('iframe[title="教学动画"]').get_attribute("sandbox") == "allow-scripts"
    child = next(f for f in page.frames if f != page.main_frame and f.url == "about:srcdoc")
    assert child.evaluate('() => {try { parent.document.body; return false; } catch { return true; }}')
    page.screenshot(path=str(out / "animation-preview-mobile.png"), full_page=True)
    page.route("**/api/forge/auth/me", lambda route: route.fulfill(status=401, json={"detail": "请先登录"}))
    page.reload(wait_until="domcontentloaded")
    expect(page.get_by_role("button", name="发送 ↗")).to_be_disabled()
    print(json.dumps({"browser": "PASS", "history_messages": len(calls[1]["history"]), "error_retry": "PASS", "mobile_no_overflow": True, "anonymous_blocked": True, "animation_iframe_interaction": True, "parent_dom_isolated": True}), flush=True)
    browser.close()
