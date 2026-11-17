"""Versioned, locally owned, schema-constrained HTML starter templates.

Templates are data, not executable Python plugins. Only bundled, reviewed template
IDs are addressable; model input cannot specify filesystem paths.
"""
import html
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1] / "templates"
IDENTIFIER = re.compile(r"^[a-z][a-z0-9-]{1,63}$")


class TemplateError(ValueError):
    pass


class TemplateCatalog:
    def __init__(self, root: Path = ROOT):
        self.root = Path(root)

    def get(self, template_id: str) -> dict[str, Any]:
        if not IDENTIFIER.fullmatch(template_id):
            raise TemplateError("Invalid template ID")
        directory = self.root / template_id
        try:
            manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
            if manifest.get("id") != template_id or not (directory / "index.html").is_file():
                raise TemplateError("Template manifest mismatch")
            return manifest
        except (FileNotFoundError, json.JSONDecodeError) as error:
            raise TemplateError("Unknown or malformed template") from error

    def search(self, query: str = "") -> list[dict[str, Any]]:
        words = query.lower().split()
        result = []
        for path in sorted(self.root.glob("*/manifest.json")):
            try:
                manifest = self.get(path.parent.name)
            except TemplateError:
                continue
            haystack = " ".join(str(manifest.get(key, "")) for key in ("id", "name", "description", "keywords")).lower()
            if not words or any(word in haystack for word in words):
                result.append({key: manifest.get(key) for key in ("id", "version", "name", "description", "keywords")})
        return result

    def render(self, template_id: str, config: dict[str, Any]) -> str:
        manifest = self.get(template_id)
        if not isinstance(config, dict):
            raise TemplateError("Configuration must be an object")
        title = config.get("title")
        cards = config.get("cards")
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 100:
            raise TemplateError("title must be a nonempty string of at most 100 characters")
        if not isinstance(cards, list) or not 1 <= len(cards) <= 40:
            raise TemplateError("cards must contain 1–40 items")
        safe_cards = []
        for item in cards:
            if not isinstance(item, dict) or set(item) != {"question", "answer"}:
                raise TemplateError("Every card needs exactly question and answer")
            question, answer = item["question"], item["answer"]
            if any(not isinstance(x, str) or not x.strip() or len(x) > 800 for x in (question, answer)):
                raise TemplateError("Card strings must contain 1–800 characters")
            safe_cards.append({"question": question, "answer": answer})
        data = {"title": title.strip(), "cards": safe_cards}
        # Escaping '<' also prevents an untrusted </script> inside JSON from closing the data element.
        serialized = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        source = (self.root / template_id / "index.html").read_text(encoding="utf-8")
        if source.count("__NAR_TEMPLATE_DATA__") != 1 or source.count("__NAR_TEMPLATE_TITLE__") != 1:
            raise TemplateError("Template placeholders are invalid")
        return source.replace("__NAR_TEMPLATE_TITLE__", html.escape(title.strip(), quote=True)).replace("__NAR_TEMPLATE_DATA__", serialized)
