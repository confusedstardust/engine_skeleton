"""The visible commentary must be real incremental model text, not fabricated dots."""
import asyncio
from types import SimpleNamespace

from app.public_brief import MAX_BRIEF_CHARS, chunk_text, stream_public_brief
from app.progress_events import enter_phase
from app.progress_stream import progress_payload, stream_progress


def test_model_chunks_are_progressively_visible():
    state = {"id": "a" * 32, "status": "RUNNING"}
    observations = []
    class FakeModel:
        async def astream(self, messages):
            assert len(messages) == 2
            assert "赤壁赋" in messages[1].content
            for piece in ("我理解你想", "把《赤壁赋》", "做成抽背互动网页。"):
                yield SimpleNamespace(content=piece)
                await asyncio.sleep(0)
                observations.append(state.get("public_brief"))

    result = asyncio.run(stream_public_brief(None, "请把赤壁赋做成抽背网页", state, model=FakeModel()))
    assert result == "我理解你想把《赤壁赋》做成抽背互动网页。"
    assert observations == [
        "我理解你想", "我理解你想把《赤壁赋》", result,
    ]
    assert progress_payload(state)["public_brief"] == result
    assert "model_trace" not in progress_payload({**state, "model_trace": {"secret": "NO"}})


def test_public_brief_text_is_bounded_and_never_exposes_intermediate_html():
    state = {"id": "b" * 32, "status": "RUNNING", "output": "<html>secret</html>",
             "artifact_id": "c" * 32, "tool_arguments": "secret"}
    class FakeModel:
        async def astream(self, _messages):
            yield SimpleNamespace(content="学习目标：" + "探索" * 900)
    result = asyncio.run(stream_public_brief(None, "函数", state, model=FakeModel()))
    assert len(result) == MAX_BRIEF_CHARS
    snapshot = progress_payload(state)
    assert len(snapshot["public_brief"]) == MAX_BRIEF_CHARS
    assert "output" not in snapshot
    assert "artifact_id" not in snapshot
    assert "tool_arguments" not in snapshot


def test_live_sse_changes_as_model_brief_grows():
    async def test_stream():
        state = {"id": "d" * 32, "status": "RUNNING"}
        enter_phase(state, "DESIGNING")
        sse = stream_progress(state, interval=0.001)
        await anext(sse)
        first = await anext(sse)
        assert "event: progress\n" in first
        state["public_brief"] = "我理解你想"
        second = await anext(sse)
        assert "我理解你想" in second
        state["public_brief"] += "学习三角函数。"
        third = await anext(sse)
        assert "学习三角函数" in third
        assert "event: progress\n" in third
        state["status"] = "SUCCEEDED"
        final = await anext(sse)
        assert "event: complete\n" in final
        return first, second, third
    asyncio.run(test_stream())


def test_chunk_text_accepts_provider_text_blocks():
    assert chunk_text(SimpleNamespace(content="连续文字")) == "连续文字"
    assert chunk_text(SimpleNamespace(content=[{"type": "text", "text": "中文"},
                                               {"type": "text", "text": "输出"},
                                               {"type": "tool_use", "text": "private"}])) == "中文输出"
