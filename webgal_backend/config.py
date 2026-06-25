from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ[key] = value


def _resolve_asset_scripts_dir(workspace_root: Path) -> Path:
    """Resolve image-generation scripts dir.

    Legacy Cursor skills used ~/.agents/skills/webgal-game/script; this
    project ships scripts in workspace_root/asset_scripts instead.
    """
    default = (workspace_root / "asset_scripts").resolve()
    configured = os.getenv("WEBGAL_ASSET_SCRIPTS_DIR")
    if not configured:
        return default

    candidate = Path(configured)
    if not candidate.is_absolute():
        candidate = (workspace_root / candidate).resolve()
    else:
        candidate = candidate.resolve()

    if not candidate.exists():
        return default if default.exists() else candidate

    # Ignore stale Cursor skill paths when the project ships local scripts.
    normalized = str(candidate).replace("\\", "/").lower()
    if default.exists() and ("/.agents/skills/" in normalized or normalized.endswith("/script")):
        return default

    return candidate


def _optional_positive_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    parsed = int(value)
    return parsed if parsed > 0 else None


def _resolve_config_path(value: str | None, workspace_root: Path, default: Path) -> Path:
    if not value:
        return default.resolve()
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    return (workspace_root / path).resolve()


@dataclass(frozen=True)
class Settings:
    workspace_root: Path
    contracts_dir: Path
    jobs_dir: Path
    llm_api_key: str | None
    llm_base_url: str
    llm_model: str
    llm_api_mode: str
    llm_thinking: str
    llm_reasoning_effort: str
    max_schema_retries: int
    max_text_retries: int
    llm_max_tokens: int | None
    asset_scripts_dir: Path
    sound_effects_dir: Path
    image_model: str

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(WORKSPACE_ROOT / ".env")
        workspace_root = Path(os.getenv("WEBGAL_BACKEND_ROOT", WORKSPACE_ROOT)).resolve()
        contracts_dir = _resolve_config_path(
            os.getenv("WEBGAL_CONTRACTS_DIR"),
            workspace_root,
            workspace_root / "webgal_backend" / "contracts",
        )
        jobs_dir = _resolve_config_path(os.getenv("WEBGAL_JOBS_DIR"), workspace_root, workspace_root / "jobs")
        asset_scripts_dir = _resolve_asset_scripts_dir(workspace_root)
        sound_effects_dir = _resolve_config_path(
            os.getenv("WEBGAL_SOUND_EFFECTS_DIR"),
            workspace_root,
            Path.home() / ".claude" / "skills" / "webgal-game" / "shared" / "bgm_repo" / "Sound effects",
        )

        return cls(
            workspace_root=workspace_root,
            contracts_dir=contracts_dir,
            jobs_dir=jobs_dir,
            llm_api_key=os.getenv("DEEPSEEK_API_KEY"),
            llm_base_url=(
                os.getenv("DEEPSEEK_BASE_URL")
                or "https://api.deepseek.com"
            ).rstrip("/"),
            llm_model=(
                os.getenv("MODEL")
                or os.getenv("DEEPSEEK_MODEL")
                or os.getenv("OPENAI_MODEL")
                or "deepseek-v4-pro"
            ),
            llm_api_mode=(os.getenv("LLM_API_MODE") or os.getenv("OPENAI_API_MODE") or "chat").lower(),
            llm_thinking=(os.getenv("DEEPSEEK_THINKING") or "enabled").lower(),
            llm_reasoning_effort=(os.getenv("DEEPSEEK_REASONING_EFFORT") or "high").lower(),
            max_schema_retries=int(os.getenv("WEBGAL_MAX_SCHEMA_RETRIES", "2")),
            max_text_retries=int(os.getenv("WEBGAL_MAX_TEXT_RETRIES", "1")),
            llm_max_tokens=_optional_positive_int(os.getenv("WEBGAL_MAX_TOKENS")),
            asset_scripts_dir=asset_scripts_dir,
            sound_effects_dir=sound_effects_dir,
            image_model=os.getenv("ARK_IMAGE_MODEL", "doubao-seedream-4-5-251128"),
        )


settings = Settings.from_env()
