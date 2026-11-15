"""Regression tests for Anatomy animation continuity across multiple chat turns."""
import asyncio
import base64
from types import SimpleNamespace

from app.artifacts import ArtifactStore
from app.intent_router import _followup_mode, _parse_mode, classify_intent
from agents.animation import animation_state


def test_followup_animation_language_stays_on_original_generator():
    history = [
        {"role": "user", "content": "做一个马达原理拆解动画"},
        {"role": "assistant", "content": "已完成动画"},
        {"role": "user", "content": "整体位置还是太靠上了，能不能居中啊"},
        {"role": "assistant", "content": "可以调整布局"},
    ]
    assert _followup_mode("整体位置还是太靠上了，能不能居中啊", history, "animation") == "edit_animation"
    assert _followup_mode("补充要求：直接给我东西啊", history, "animation") == "edit_animation"
    assert _followup_mode("把动画中的按钮往下挪一点", history, "animation") == "edit_animation"
    assert _followup_mode("整体位置太靠上了，改成居中", history, "html") == "edit"
    assert _followup_mode("整体位置太靠上了", history, None) is None
    assert _followup_mode("重新做一个不同的动画", history, "animation") is None


def test_parser_blocks_cross_generator_edit_without_an_animation():
    assert _parse_mode('{"mode":"edit_animation"}', has_editable_html=False, current_artifact_kind=None) == "chat"
    assert _parse_mode('{"mode":"edit"}', has_editable_html=False, current_artifact_kind="animation") == "edit_animation"
    assert _parse_mode('{"mode":"html"}', has_editable_html=False, current_artifact_kind="animation") == "html"


def test_model_must_respect_recent_animation_even_if_it_says_html(monkeypatch):
    import app.intent_router as router

    class FakeModel:
        def __init__(self, **kwargs):
            pass

        async def ainvoke(self, messages):
            return SimpleNamespace(content='{"mode":"html"}')

    monkeypatch.setattr(router, "ChatOpenAI", FakeModel)
    config = SimpleNamespace(model="test", api_key=SimpleNamespace(get_secret_value=lambda: "secret"),
                             base_url="https://invalid.example", timeout_seconds=20)
    route = asyncio.run(classify_intent(
        config, "刚才那一个，直接改成居中就行", [{"role": "user", "content": "做马达动画"}],
        has_editable_html=False, current_artifact_kind="animation"))
    assert route == "edit_animation"
    new = asyncio.run(classify_intent(
        config, "重新做一个新网页", [], has_editable_html=False, current_artifact_kind="animation"))
    assert new == "html"


def test_owner_scoped_animation_source_read_and_virtual_reference(tmp_path):
    store = ArtifactStore(str(tmp_path))
    encoded = lambda content: base64.b64encode(content).decode()
    source = "import * as kit from '/opt/anatomy/kit/iso-kit.mjs';\n// motor demo"
    artifact_id = store.save("owner-1", {
        "index.html": encoded(b"<html><body>motor</body></html>"),
        "preview.png": encoded(b"png"),
        "mobile.png": encoded(b"mobile"),
        "report": {"passed": True},
    }, source, kind="animation")
    assert store.source("owner-1", artifact_id, kind="animation") == source
    import pytest
    with pytest.raises(FileNotFoundError):
        store.source("owner-2", artifact_id, kind="animation")
    with pytest.raises(FileNotFoundError):
        store.source("owner-1", artifact_id, kind="html")
    state = animation_state("把画面居中", [], parent_source=source)
    assert "/reference/current-animation/build.mjs" in state["files"]
    assert "修改已经完成的动画" in state["messages"][-1]["content"]
    assert "调用 build_animation" in state["messages"][-1]["content"]
