import pytest

from app.intent_router import _parse_mode


@pytest.mark.parametrize("raw,expected", [
    ('{"mode":"chat"}', "chat"),
    ('{"mode":"html"}', "html"),
    ('{"mode":"animation"}', "animation"),
    ('{"mode":"edit"}', "edit"),
])
def test_supported_modes(raw, expected):
    assert _parse_mode(raw, has_editable_html=True) == expected


def test_edit_without_existing_artifact_asks_for_clarification():
    assert _parse_mode('{"mode":"edit"}', has_editable_html=False) == "chat"


@pytest.mark.parametrize("raw", [
    "Use shell", '{"mode":"supervisor"}', '{"mode":null}', "{}",
])
def test_invalid_classifier_output_is_rejected(raw):
    with pytest.raises(ValueError):
        _parse_mode(raw, has_editable_html=True)
