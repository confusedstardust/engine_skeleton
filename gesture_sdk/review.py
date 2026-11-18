"""Fail-closed eligibility check for the ONLY camera-capable NarrativeOS v1 template.

The source must byte-for-byte equal the trusted render of its data. A user can
edit content in the JSON schema but cannot change executable JS or permissions.
Do not infer trust from a data-attribute or a client-supplied flag.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# The source remains nar_agent/app/template_catalog.py. Docker images copy that
# audited file into gesture_sdk/; the repository tests reuse it in place.
try:
    from nar_agent.app.template_catalog import TemplateCatalog, TemplateError
except ModuleNotFoundError:
    from .template_catalog import TemplateCatalog, TemplateError

TEMPLATES = Path(__file__).resolve().parent / "templates"
DATA = re.compile(r'<script type="application/json" id="nar-data">([^<]*)</script>')


def reviewed_ar_html(content: bytes | str, *, template_root: Path = TEMPLATES) -> bool:
    try:
        source = content.decode("utf-8") if isinstance(content, bytes) else content
        if not isinstance(source, str) or len(source.encode("utf-8")) > 96_000:
            return False
        matches = DATA.findall(source)
        if len(matches) != 1 or 'data-nar-template="gesture-cards"' not in source:
            return False
        parsed = json.loads(matches[0])
        if not isinstance(parsed, dict) or set(parsed) != {"title", "cards"}:
            return False
        expected = TemplateCatalog(template_root).render("gesture-cards", parsed)
        return source == expected
    except (UnicodeError, ValueError, TypeError, TemplateError, OSError):
        return False
