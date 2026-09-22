from __future__ import annotations

from pathlib import Path
from typing import Any

import jsonschema

from .config import settings
from .generation_limits import generation_limits
from .storage import read_json


class ValidationFailure(RuntimeError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("\n".join(errors))
        self.errors = errors


def validate_schema(schema_name: str, artifact: dict[str, Any]) -> None:
    schema_path = settings.contracts_dir / "schemas" / schema_name
    schema = read_json(schema_path)
    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)
    errors = sorted(validator.iter_errors(artifact), key=lambda error: list(error.path))
    if errors:
        messages = []
        for error in errors:
            location = ".".join(str(part) for part in error.path) or "<root>"
            messages.append(f"{location}: {error.message}")
        raise ValidationFailure(messages)


def semantic_asset_manifest(manifest: dict[str, Any], plan: dict[str, Any], expected_base_dir: str) -> None:
    limits = generation_limits()
    errors: list[str] = []
    if Path(manifest["base_dir"]).resolve() != Path(expected_base_dir).resolve():
        errors.append(f"base_dir must be {expected_base_dir}, got {manifest['base_dir']}")

    character_ids = {character["id"] for character in plan.get("characters", [])}
    figure_names = set()
    for image in manifest["images"]:
        filename = image["filename"]
        subdir = image["subdir"]
        size = image["size"]
        prompt = image["prompt"]
        if subdir == limits["assets"]["figure_subdir"] or filename.startswith("figure_"):
            if image["subdir"] != limits["assets"]["figure_subdir"] or image["size"] != limits["assets"]["figure_size"]:
                errors.append(f"{filename} figure must use {limits['assets']['figure_subdir']}/{limits['assets']['figure_size']}")
            figure_names.add(filename.removeprefix("figure_"))
        else:
            if image["subdir"] != limits["assets"]["background_subdir"] or image["size"] != limits["assets"]["background_size"]:
                errors.append(f"{filename} background/cg must use {limits['assets']['background_subdir']}/{limits['assets']['background_size']}")

    missing_figures = [
        character_id
        for character_id in character_ids
        if character_id not in figure_names and not any(character_id in figure_name for figure_name in figure_names)
    ]
    if missing_figures:
        errors.append(f"missing figure assets for characters: {sorted(missing_figures)}")

    if errors:
        raise ValidationFailure(errors)


def semantic_quiz_plan(plan: dict[str, Any]) -> None:
    errors: list[str] = []
    question_ids: set[str] = set()
    question_types: set[str] = set()
    for index, question in enumerate(plan.get("questions", [])):
        prefix = f"questions.{index}"
        question_id = str(question.get("id", ""))
        if question_id in question_ids:
            errors.append(f"{prefix}.id must be unique")
        question_ids.add(question_id)
        question_type = str(question.get("type", ""))
        question_types.add(question_type)
        options = question.get("options", [])
        option_ids = [str(option.get("id", "")) for option in options if isinstance(option, dict)]
        if len(option_ids) != len(set(option_ids)):
            errors.append(f"{prefix}.options ids must be unique")
        correct = question.get("correct_option_ids", [])
        if len(correct) != 1 or str(correct[0]) not in option_ids:
            errors.append(f"{prefix}.correct_option_ids must contain exactly one existing option id")
        if question_type == "single_choice" and len(options) != 4:
            errors.append(f"{prefix}.options must contain four options for single_choice")
        if question_type == "judgement":
            option_texts = {str(option.get("text", "")).strip() for option in options if isinstance(option, dict)}
            if len(options) != 2 or option_texts != {"正确", "错误"}:
                errors.append(f"{prefix}.options must be 正确 and 错误 for judgement")
    if not {"single_choice", "judgement"}.issubset(question_types):
        errors.append("questions must include both single_choice and judgement")
    if errors:
        raise ValidationFailure(errors)
