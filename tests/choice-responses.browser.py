"""Exercise the real workbench UI with browser-local API fixtures only."""
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright, expect


def run():
    job = {"id": "a" * 32, "title": "荒原家园", "status": "GAME_DESIGN_COMPLETED",
           "phase": "GAME_DESIGN_COMPLETION", "has_published_build": False, "draft_revision": 1,
           "options": {"generation_mode": "manual"}}
    design = {"version": 1, "scenes": [
        {"scene_file": "start.txt", "title": "从看开始", "lines": [
            {"id": "opening", "kind": "narration", "speaker": "旁白", "text": "荒原家园的第一步，竟然要从看开始。", "rawPrefix": "旁白"},
            {"id": "choice", "kind": "choice", "speaker": "分支", "text": "", "rawPrefix": "choose", "choices": [
                {"id": "stay", "text": "观察生活系统", "target": "continue_choice_intro"},
                {"id": "leave", "text": "找阿曜试车", "target": "next.txt"}]},
            {"id": "merge", "kind": "branch", "speaker": "分支", "text": "continue_choice_intro", "branchLabel": "continue_choice_intro", "rawPrefix": "branch"},
            {"id": "common", "kind": "narration", "speaker": "旁白", "text": "荒原家园的模拟训练，从生活系统开始。", "rawPrefix": "旁白"},
            {"id": "exit", "kind": "command", "text": "changeScene:next.txt;", "rawPrefix": "changeScene"}]},
        {"scene_file": "next.txt", "marker": "Ending", "title": "九大舱体的秘密", "lines": [
            {"id": "ending", "kind": "narration", "speaker": "旁白", "text": "新的旅程开始。", "rawPrefix": "旁白"}]}]}
    saved = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel="chrome")
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def respond(route):
            nonlocal design
            path = route.request.url.split("?")[0]
            if path.endswith("/auth/me"):
                data = {"id": "owner", "name": "Owner"}
            elif path.endswith("/nodes"):
                data = {"job": job, "scenes": [], "nodes": [
                    {"key": "narrative_plan", "exists": True, "content": json.dumps({"title": "荒原家园", "characters": [{"name": "我"}, {"name": "阿曜"}]})},
                    {"key": "game_design_completed", "exists": True, "content": json.dumps(design)}]}
            elif path.endswith("/assets/review"):
                data = {"assets": [], "voices": [], "available_voices": [], "scene_music": [], "music_assets": []}
            elif path.endswith("/artifacts"):
                design = json.loads(route.request.post_data_json["content"])
                saved.append(design)
                data = {"saved": True, "job": job}
            else:
                data = {"job": job}
            route.fulfill(json=data)

        page.route("**/api/**", respond)
        base = os.environ.get("WORKBENCH_TEST_URL", "http://127.0.0.1:3001")
        page.goto(f"{base}/jobs/{job['id']}/", wait_until="domcontentloaded")
        summaries = page.locator(".laper-choice-responses summary")
        expect(summaries).to_have_count(2)
        summaries.nth(0).click()
        first = page.locator(".laper-choice-option").nth(0)
        first.get_by_role("button", name="＋ 对白", exact=True).click()
        first.get_by_role("textbox", name="第 1 句专属对话").fill("先看看水和空气从哪里来。")
        first.get_by_role("button", name="＋ 旁白", exact=True).click()
        first.get_by_role("textbox", name="第 2 句专属对话").fill("我抬头望向生活舱。")
        handle = first.get_by_role("button", name="拖动专属对话排序", exact=True).nth(1)
        handle.scroll_into_view_if_needed()
        source = handle.bounding_box()
        target = first.locator("[data-response-line]").nth(0).bounding_box()
        page.mouse.move(source["x"] + source["width"] / 2, source["y"] + source["height"] / 2)
        page.mouse.down()
        page.mouse.move(target["x"] + target["width"] / 2, target["y"] + 10, steps=8)
        expect(first.locator(".laper-response-line.dragging")).to_have_count(1)
        expect(first.locator(".laper-response-line.drop-before")).to_have_count(1)
        page.mouse.up()
        expect(first.get_by_role("textbox", name="第 1 句专属对话")).to_have_value("我抬头望向生活舱。")
        summaries.nth(1).click()
        second = page.locator(".laper-choice-option").nth(1)
        second.get_by_role("button", name="＋ 对白", exact=True).click()
        second.get_by_role("textbox", name="第 1 句专属对话").fill("阿曜，带我去看看动力舱。")
        second.get_by_role("combobox", name="跳转场景").click()
        page.get_by_role("option", name="留在当前场景（互动后继续）", exact=True).click()
        expect(second.get_by_role("textbox", name="第 1 句专属对话")).to_have_value("阿曜，带我去看看动力舱。")
        second.get_by_role("combobox", name="跳转场景").click()
        page.get_by_role("option", name="结局：九大舱体的秘密", exact=True).click()
        expect(second.get_by_role("textbox", name="第 1 句专属对话")).to_have_value("阿曜，带我去看看动力舱。")
        output = Path(__file__).resolve().parents[1] / "design-previews" / "choice-responses-workbench.png"
        page.locator(".laper-choice-list").screenshot(path=str(output))
        page.get_by_role("button", name="保存并生成素材", exact=True).click()
        page.wait_for_function("document.body.innerText.includes('审阅素材资产')")
        assert saved, "Expected real save handler to send the structured draft"
        options = saved[-1]["scenes"][0]["lines"][1]["choices"]
        assert options[0]["response_lines"][0]["text"] == "我抬头望向生活舱。"
        assert options[1]["response_lines"][0]["text"] == "阿曜，带我去看看动力舱。"
        assert options[0]["target"] == "continue_choice_intro"
        assert options[1]["target"] == "next.txt"
        page.reload(wait_until="domcontentloaded")
        summaries = page.locator(".laper-choice-responses summary")
        expect(summaries).to_have_count(2)
        summaries.nth(0).click()
        expect(page.locator(".laper-choice-option").nth(0).get_by_role("textbox", name="第 1 句专属对话")).to_have_value("我抬头望向生活舱。")
        assert not errors, errors
        browser.close()
        print("PASS: real workbench response add/edit/reorder, mixed exits, save and reload; screenshot:", output)


if __name__ == "__main__":
    run()
