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

    Function-call mode (WEBGAL_SKILL_DIR) is separate from asset scripts.
    Legacy Cursor skills used ~/.agents/skills/webgal-game/script; this project
    ships scripts in workspace_root/asset_scripts instead.
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


@dataclass(frozen=True)
class Settings:
    workspace_root: Path
    skill_dir: Path
    jobs_dir: Path
    llm_api_key: str | None
    llm_base_url: str
    llm_model: str
    llm_api_mode: str
    llm_thinking: str
    llm_reasoning_effort: str
    max_schema_retries: int
    max_repair_cycles: int
    llm_max_tokens: int | None
    asset_scripts_dir: Path

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(WORKSPACE_ROOT / ".env")
        workspace_root = Path(os.getenv("WEBGAL_BACKEND_ROOT", WORKSPACE_ROOT)).resolve()
        skill_dir = Path(
            os.getenv("WEBGAL_SKILL_DIR", workspace_root / "webgal-game-function-call")
        ).resolve()
        jobs_dir = Path(os.getenv("WEBGAL_JOBS_DIR", workspace_root / "jobs")).resolve()
        asset_scripts_dir = _resolve_asset_scripts_dir(workspace_root)

        return cls(
            workspace_root=workspace_root,
            skill_dir=skill_dir,
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
            max_repair_cycles=int(os.getenv("WEBGAL_MAX_REPAIR_CYCLES", "3")),
            llm_max_tokens=_optional_positive_int(os.getenv("WEBGAL_MAX_TOKENS")),
            asset_scripts_dir=asset_scripts_dir,
        )


settings = Settings.from_env()
