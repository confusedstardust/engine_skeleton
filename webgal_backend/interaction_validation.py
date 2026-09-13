"""Server-side interaction-v1 validation using the same checked-in Schema source."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from jsonschema import Draft7Validator

SCHEMA_PATH = Path(__file__).resolve().parents[1] / 'contracts' / 'interactions' / 'interaction-v1.schema.json'

def validate_interaction_config(config: dict[str, Any]) -> None:
    """Raise ValueError with publish-safe diagnostics; never execute configuration content."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding='utf-8'))
    errors = sorted(Draft7Validator(schema).iter_errors(config), key=lambda error: list(error.path))
    if errors:
        raise ValueError('interaction-v1 invalid: ' + '; '.join(error.message for error in errors))
    config_path = config.get('_path', '')
    if config_path and (not config_path.startswith('interactions/') or '..' in config_path or config_path.startswith('/')):
        raise ValueError('interaction config path must remain under interactions/')
