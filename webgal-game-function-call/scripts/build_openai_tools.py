#!/usr/bin/env python3
"""Inline local schema references in OpenAI tool definitions.

The source `references/openai-tools.json` keeps schemas maintainable by using
local refs like `schemas/narrative_plan.schema.json`. This script expands those
refs so the resulting JSON can be sent directly as OpenAI `tools`.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_pointer(document: dict[str, Any], pointer: str) -> Any:
    if not pointer.startswith("#/"):
        raise ValueError(f"unsupported JSON pointer: {pointer}")

    current: Any = document
    for raw_part in pointer[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        current = current[part]
    return copy.deepcopy(current)


def inline_refs(value: Any, base_dir: Path, root: dict[str, Any] | None = None) -> Any:
    if isinstance(value, list):
        return [inline_refs(item, base_dir, root) for item in value]

    if not isinstance(value, dict):
        return value

    if set(value) == {"$ref"} and isinstance(value["$ref"], str):
        ref = value["$ref"]
        if ref.startswith("#/"):
            if root is None:
                return value
            return inline_refs(resolve_pointer(root, ref), base_dir, root)
        if ref.startswith("schemas/") and ref.endswith(".json"):
            schema = load_json(base_dir / ref)
            schema = copy.deepcopy(schema)
            schema.pop("$schema", None)
            schema.pop("$id", None)
            return inline_refs(schema, base_dir, schema)

    result = {}
    for key, item in value.items():
        if key == "$defs":
            continue
        result[key] = inline_refs(item, base_dir, root)
    return result


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: build_openai_tools.py <openai-tools.json> <output.json>", file=sys.stderr)
        return 2

    source = Path(sys.argv[1])
    output = Path(sys.argv[2])
    tools = load_json(source)
    built = inline_refs(tools, source.parent)
    output.write_text(json.dumps(built, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
