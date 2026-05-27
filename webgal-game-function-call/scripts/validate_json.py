#!/usr/bin/env python3
"""Validate a JSON artifact against a JSON Schema.

Usage:
  python scripts/validate_json.py references/schemas/narrative_plan.schema.json state/narrative_plan.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: validate_json.py <schema.json> <artifact.json>", file=sys.stderr)
        return 2

    try:
        import jsonschema
    except ImportError:
        print("jsonschema is required: pip install jsonschema", file=sys.stderr)
        return 2

    schema_path = Path(sys.argv[1])
    artifact_path = Path(sys.argv[2])

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)
    errors = sorted(validator.iter_errors(artifact), key=lambda error: list(error.path))

    if errors:
        for error in errors:
            location = ".".join(str(part) for part in error.path) or "<root>"
            print(f"{location}: {error.message}", file=sys.stderr)
        return 1

    print(f"valid: {artifact_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
