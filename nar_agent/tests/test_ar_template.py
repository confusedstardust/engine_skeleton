"""Bridge template is valid offline and never includes camera code."""
from pathlib import Path

import pytest

from app.template_catalog import TemplateCatalog, TemplateError

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"


def test_ar_template_discovery_and_safe_json():
    catalog = TemplateCatalog(TEMPLATES)
    results = catalog.search("手势")
    assert any(item["id"] == "gesture-cards" for item in results)
    source = catalog.render("gesture-cards", {
        "title": "</script><script>alert(1)</script>",
        "cards": [{"question": "<script>test</script>", "answer": "安全"}],
    })
    assert "__NAR_TEMPLATE_DATA__" not in source
    assert "\\u003cscript" in source
    assert source.count("data-nar-template=\"gesture-cards\"") == 1
    assert "getUserMedia" not in source
    assert 'data-nar-gesture="v1"' in source
    assert "window.NarrativeGesture" in source
    assert "getUserMedia" not in source
    assert "/gesture-sdk/" not in source
    assert "approvedOrigin" not in source


@pytest.mark.parametrize("cards", [[], [{"question": "", "answer": "yes"}], [{"question": "q"}]])
def test_ar_template_rejects_invalid_cards(cards):
    with pytest.raises(TemplateError):
        TemplateCatalog(TEMPLATES).render("gesture-cards", {"title": "测试", "cards": cards})
