from playwright.sync_api import sync_playwright, expect


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, channel="chrome")
    page = browser.new_page()
    job = {"id": "a" * 32, "title": "共享操作测试", "status": "DONE", "has_published_build": True, "build_state": "CURRENT"}
    state = {"published": False, "fail_remove": True, "fail_title": True}

    def respond(route):
        path = route.request.url.split("?")[0]
        method = route.request.method
        if path.endswith("/auth/me"):
            data = {"id": "owner", "name": "Owner"}
        elif path.endswith("/jobs"):
            data = {"jobs": [job]}
        elif path.endswith("/nodes"):
            data = {"job": job, "nodes": [], "scenes": []}
        elif path.endswith("/assets/review"):
            data = {"assets": [], "voices": [], "available_voices": [], "scene_music": [], "music_assets": [], "particle_effects": {"effects": [], "scenes": []}}
        elif path.endswith("/ecosystem-publication"):
            if method == "DELETE" and state["fail_remove"]:
                return route.fulfill(status=503, json={"detail": "取消发布暂时不可用"})
            if method == "POST":
                state["published"] = True
            elif method == "DELETE":
                state["published"] = False
            data = {"published": state["published"]}
        elif path.endswith("/title"):
            if state["fail_title"]:
                return route.fulfill(status=503, json={"detail": "重命名暂时不可用"})
            job["title"] = route.request.post_data_json["title"]
            data = {"job": job}
        elif path.endswith("/quiz"):
            data = {"status": "NOT_GENERATED", "quiz": None}
        else:
            data = {}
        route.fulfill(json=data)

    page.route("**/api/**", respond)
    page.route("**/play/**", lambda route: route.fulfill(status=404))
    page.goto("http://127.0.0.1:3106/history/")
    page.get_by_role("button", name="作品操作：共享操作测试").click()
    page.get_by_role("menuitem", name="发布", exact=True).click()
    expect(page.get_by_text("已发布到教师资源广场。", exact=True)).to_be_visible()
    page.goto(f"http://127.0.0.1:3106/jobs/{job['id']}/")
    expect(page.get_by_role("button", name="更新发布", exact=True)).to_be_visible()
    page.get_by_role("button", name="取消生态发布", exact=True).click()
    page.get_by_role("alertdialog").get_by_role("button", name="确认", exact=True).click()
    expect(page.get_by_text("请求失败（HTTP 503）：取消发布暂时不可用", exact=True)).to_be_visible()
    state["fail_remove"] = False
    page.get_by_role("button", name="取消生态发布", exact=True).click()
    page.get_by_role("alertdialog").get_by_role("button", name="确认", exact=True).click()
    expect(page.get_by_text("已取消生态发布。", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="发布", exact=True)).to_be_visible()
    page.get_by_role("button", name="修改游戏名称").click()
    title = page.get_by_role("textbox", name="游戏名称")
    title.fill(" ")
    title.press("Enter")
    expect(page.get_by_text("作品名称需为 1–160 个字符。", exact=True)).to_be_visible()
    title.fill("新作品名称")
    title.press("Enter")
    expect(page.get_by_text("请求失败（HTTP 503）：重命名暂时不可用", exact=True)).to_be_visible()
    state["fail_title"] = False
    title.fill("新作品名称")
    title.press("Enter")
    expect(page.locator(".completion-title-display strong")).to_have_text("新作品名称")
    page.goto("http://127.0.0.1:3106/history/")
    expect(page.get_by_role("button", name="作品操作：新作品名称")).to_be_visible()
    browser.close()
    print("shared work actions: history publish, completion unpublish retry, title validation/error/retry passed")
