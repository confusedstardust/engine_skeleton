"""Normalize optional NarAgent choice envelopes before persisting public chat.

Models sometimes emit malformed or truncated protocol JSON. Never expose it.
"""
import json
import re

_START = re.compile(r"\[\[\s*NAR_UI_CHOICES_V1\s*\]\]", re.I)
_END = re.compile(r"\[\[\s*/\s*NAR_UI_CHOICES_V1\s*\]\]", re.I)


def normalize_agent_choice(output: str) -> tuple[str, dict | None]:
    match = _START.search(output)
    if not match:
        return output, None
    body = output[:match.start()].rstrip()
    end = _END.search(output, match.end())
    if not end:
        return body or "请说明你希望下一步怎么做。", None
    raw = output[match.end():end.start()].strip()
    fence = chr(96) * 3
    if raw.startswith(fence):
        raw = re.sub(r"^"+re.escape(fence)+r"(?:json)?\s*|\s*"+re.escape(fence)+r"$", "", raw, flags=re.I).strip()
    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or not isinstance(data.get("question"), str):
            raise ValueError
        options = data.get("options")
        if not isinstance(options, list) or not 2 <= len(options) <= 6:
            raise ValueError
        if not data["question"].strip() or len(data["question"]) > 300:
            raise ValueError
        ids = set()
        for opt in options:
            if not isinstance(opt, dict):
                raise ValueError
            ident, label = opt.get("id"), opt.get("label")
            if (not isinstance(ident, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,16}", ident)
                or ident in ids or not isinstance(label, str) or not 0 < len(label.strip()) <= 240):
                raise ValueError
            ids.add(ident)
        choice = {
            "question": data["question"].strip(),
            "options": [{"id": x["id"], "label": x["label"].strip(),
                         **({"description": x["description"][:240]} if isinstance(x.get("description"), str) else {})}
                        for x in options],
            "multiple": bool(data.get("multiple", False)),
            "allowCustom": bool(data.get("allowCustom", True)),
        }
        return body, choice
    except (ValueError, TypeError, KeyError):
        return body or "请说明你希望下一步怎么做。", None


def visible_stream_prefix(output: str) -> str:
    """Prevent partial delimiter fragments from flashing while tokens arrive."""
    match = _START.search(output)
    if match:
        return output[:match.start()].rstrip()
    signature = "[[NAR_UI_CHOICES_V1]]"
    for length in range(min(len(signature) - 1, len(output)), 0, -1):
        if output[-length:].lower() == signature[:length].lower():
            return output[:-length]
    return output
