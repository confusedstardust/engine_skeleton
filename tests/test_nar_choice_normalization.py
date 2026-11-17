import json
from datetime import datetime, timezone

from webgal_backend.nar_choice_protocol import normalize_agent_choice, visible_stream_prefix
from webgal_backend.nar_conversation_store import _message


def test_screenshot_style_choice_is_metadata_not_visible_json():
    raw = ("我可以继续做下列内容。\n[[NAR_UI_CHOICES_V1]]\n" + json.dumps({
        "question": "接下来你想让我先做哪一项？",
        "options": [
            {"id": "a", "label": "分镜与页面布局说明：画布、元件栏、读数面板和操作顺序怎么走"},
            {"id": "b", "label": "可交给开发的交互与状态规格：每个状态的数据结构、按钮行为、错误提示文案"},
            {"id": "c", "label": "学生任务单加5道检测题，可以直接打印使用"},
            {"id": "d", "label": "把整个方案缩到一页纸的精简版，方便给教研组看"},
        ], "multiple": False, "allowCustom": True,
    }, ensure_ascii=False) + "\n[[/NAR_UI_CHOICES_V1]]")
    body, choices = normalize_agent_choice(raw)
    assert body == "我可以继续做下列内容。"
    assert len(choices["options"]) == 4
    row = {"id": "a", "seq": 3, "role": "assistant", "content": raw,
           "created_at": datetime.now(timezone.utc), "public_metadata": None}
    rendered = _message(row)
    assert "[[NAR_UI_CHOICES_V1]]" not in rendered["content"]
    assert rendered["metadata"]["choices"] == choices


def test_malformed_or_unterminated_protocol_is_suppressed():
    for value in ('{"question":', '{"question":"yes","options":[]}'):
        text = "正常答复\n[[NAR_UI_CHOICES_V1]]\n" + value
        assert normalize_agent_choice(text) == ("正常答复", None)
    assert normalize_agent_choice("普通教学解释") == ("普通教学解释", None)


def test_partial_stream_marker_never_flashes_in_visible_reply():
    prefix = "教材内容"
    for suffix in ("[", "[[", "[[NAR_", "[[NAR_UI_CHOICES_V1]]"):
        assert visible_stream_prefix(prefix + suffix) == prefix
