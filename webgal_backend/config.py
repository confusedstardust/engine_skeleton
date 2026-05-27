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
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    workspace_root: Path
    skill_dir: Path
    jobs_dir: Path
    llm_api_key: str | None
    llm_base_url: str
    llm_model: str
    llm_api_mode: str
    max_schema_retries: int
    max_repair_cycles: int
    asset_scripts_dir: Path

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(WORKSPACE_ROOT / ".env")
        workspace_root = Path(os.getenv("WEBGAL_BACKEND_ROOT", WORKSPACE_ROOT)).resolve()
        skill_dir = Path(
            os.getenv("WEBGAL_SKILL_DIR", workspace_root / "webgal-game-function-call")
        ).resolve()
        jobs_dir = Path(os.getenv("WEBGAL_JOBS_DIR", workspace_root / "jobs")).resolve()
        default_asset_scripts = workspace_root / "asset_scripts"
        asset_scripts_dir = Path(
            os.getenv("WEBGAL_ASSET_SCRIPTS_DIR", str(default_asset_scripts))
        ).resolve()

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
                or "deepseek-chat"
            ),
            llm_api_mode=(os.getenv("LLM_API_MODE") or os.getenv("OPENAI_API_MODE") or "chat").lower(),
            max_schema_retries=int(os.getenv("WEBGAL_MAX_SCHEMA_RETRIES", "2")),
            max_repair_cycles=int(os.getenv("WEBGAL_MAX_REPAIR_CYCLES", "3")),
            asset_scripts_dir=asset_scripts_dir,
        )


settings = Settings.from_env()
