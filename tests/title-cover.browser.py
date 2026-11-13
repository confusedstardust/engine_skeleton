"""Run against a local workbench with API responses isolated to this browser."""
from io import BytesIO
from PIL import Image
from playwright.sync_api import sync_playwright, expect


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, channel="chrome")
    page = browser.new_page()
    job = {"id": "a" * 32, "title": "封面测试", "status": "DONE", "has_published_build": True, "build_state": "CURRENT", "draft_revision": 1, "published_revision": 1}
    requests = []

    def respond(route):
        path = route.request.url.split("?")[0]
        if path.endswith("/auth/me"):
            data = {"id": "owner", "name": "Owner"}
        elif path.endswith("/jobs"):
            data = {"jobs": [job]}
        elif path.endswith("/ecosystem-publication"):
            data = {"published": False}
        elif path.endswith("/title"):
            job["title"] = route.request.post_data_json["title"]
            data = {"job": job}
        elif path.endswith("/published-flow"):
            data = {"nodes": [], "edges": [], "warnings": [], "revision": 1}
        elif path.endswith("/assets"):
            data = {"assets": [{"file_id": "b" * 32, "name": "素材库背景", "mime_type": "image/webp", "url": "/placeholder.webp"}], "has_more": False}
        elif path.endswith(("/assets/upload", "/assets/from-library")):
            requests.append(route.request)
            job["cover_revision"] = job.get("cover_revision", 0) + 1
            data = {"job": job, "asset": {"filename": "cover.webp"}}
        else:
            data = {}
        route.fulfill(json=data)

    page.route("**/api/**", respond)
    preview = BytesIO()
    Image.new("RGB", (32, 18), "blue").save(preview, "PNG")
    page.route("**/play/**", lambda route: route.fulfill(status=404) if "cover=0" in route.request.url else route.fulfill(body=preview.getvalue(), content_type="image/png"))
    page.route("**/placeholder.webp", lambda route: route.fulfill(body=preview.getvalue(), content_type="image/png"))
    page.goto("http://127.0.0.1:3106/history/")
    page.wait_for_load_state("networkidle")
    more = page.get_by_role("button", name="作品操作：封面测试")
    expect(page.locator(".history-cover")).to_have_text("无封面")
    more.click()
    page.get_by_role("menuitem", name="编辑封面", exact=True).click()
    dialog = page.get_by_role("dialog", name="编辑封面")
    expect(dialog.get_by_role("button", name="上传图片", exact=True)).to_be_visible()
    expect(dialog.get_by_text("无封面", exact=True)).to_be_visible()
    image = BytesIO()
    Image.new("RGB", (32, 18), "blue").save(image, "PNG")
    dialog.locator('input[type="file"]').set_input_files({"name": "cover.png", "mimeType": "image/png", "buffer": image.getvalue()})
    expect(dialog).to_have_count(0)
    expect(page.locator(".history-cover img")).to_have_attribute("src", f"/play/{job['id']}/cover?revision=1&cover=1")
    assert b'name="title_cover"' in requests[0].post_data_buffer
    more.click()
    page.get_by_role("menuitem", name="编辑封面", exact=True).click()
    page.get_by_role("button", name="从素材库选择", exact=True).click()
    picker = page.get_by_role("dialog", name="选择游戏封面").last
    picker.get_by_text("素材库背景", exact=True).click()
    page.get_by_role("button", name="使用此素材").click()
    expect(page.locator(".history-cover img")).to_have_attribute("src", f"/play/{job['id']}/cover?revision=1&cover=2")
    assert requests[1].post_data_json["title_cover"] is True
    more.click()
    page.get_by_role("menuitem", name="流程图", exact=True).click()
    flow = page.get_by_role("dialog", name="最新剧情流程图")
    expect(flow).to_be_visible()
    page.keyboard.press("Escape")
    expect(flow).to_have_count(0)
    more.click()
    page.get_by_role("menuitem", name="流程图", exact=True).click()
    expect(flow).to_be_visible()
    page.locator(".flow-modal-layer").click(position={"x": 4, "y": 4})
    expect(flow).to_have_count(0)
    more.click()
    page.get_by_role("menuitem", name="重命名", exact=True).click()
    rename = page.get_by_role("dialog", name="重命名作品")
    rename.get_by_role("textbox", name="作品名称").fill("按钮提交测试")
    rename.get_by_role("textbox", name="作品名称").press("Enter")
    expect(rename).to_have_count(0)
    expect(page.get_by_role("button", name="作品操作：按钮提交测试")).to_be_visible()
    browser.close()
    print("missing cover, image recovery, upload, library selection, flow dialog Escape and outside close passed")

