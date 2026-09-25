from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
DOUBAO_IMAGE_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DOUBAO_IMAGE_MODEL = "doubao-seedream-4-5-251128"
DOUBAO_IMAGE_API_KEY_ENV = "ARK_API_KEY"


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
    mimo_api_key: str | None
    mimo_base_url: str
    mimo_model: str
    kimi_api_key: str | None
    kimi_base_url: str
    kimi_model: str
    max_schema_retries: int
    max_text_retries: int
    max_advanced_phase_retries: int
    llm_max_tokens: int | None
    asset_scripts_dir: Path
    sound_effects_dir: Path
    image_base_url: str
    image_model: str
    image_api_key_env: str
    qwen_image_base_url: str
    qwen_image_api_key_env: str
    oss_bucket: str | None
    oss_endpoint: str
    oss_access_key_id: str | None
    oss_access_key_secret: str | None
    oss_prefix: str
    oss_access_mode: str
    oss_signed_url_ttl: int
    database_url: str | None
    asset_library_enabled: bool
    database_job_store_enabled: bool

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
            mimo_api_key=os.getenv("MIMO_API_KEY"),
            mimo_base_url=(os.getenv("MIMO_BASE_URL") or "https://api.xiaomimimo.com/v1").rstrip("/"),
            mimo_model=os.getenv("MIMO_MODEL") or "MiMo-V2.5-Pro-UltraSpeed",
            kimi_api_key=os.getenv("MOONSHOT_API_KEY"),
            kimi_base_url=(os.getenv("KIMI_BASE_URL") or "https://api.moonshot.cn/v1").rstrip("/"),
            kimi_model=os.getenv("KIMI_MODEL") or "kimi-k2.7-code-highspeed",
            max_schema_retries=int(os.getenv("WEBGAL_MAX_SCHEMA_RETRIES", "2")),
            max_text_retries=int(os.getenv("WEBGAL_MAX_TEXT_RETRIES", "1")),
            max_advanced_phase_retries=max(0, int(os.getenv("WEBGAL_MAX_ADVANCED_PHASE_RETRIES", "2"))),
            llm_max_tokens=_optional_positive_int(os.getenv("WEBGAL_MAX_TOKENS")),
            asset_scripts_dir=asset_scripts_dir,
            sound_effects_dir=sound_effects_dir,
            image_base_url=(
                os.getenv("ARK_IMAGE_BASE_URL")
                or DOUBAO_IMAGE_BASE_URL
            ).rstrip("/"),
            image_model=DOUBAO_IMAGE_MODEL,
            image_api_key_env=DOUBAO_IMAGE_API_KEY_ENV,
            qwen_image_base_url=(
                os.getenv("QWEN_IMAGE_BASE_URL")
                or "https://dashscope.aliyuncs.com/api/v1"
            ).rstrip("/"),
            qwen_image_api_key_env=(os.getenv("QWEN_IMAGE_API_KEY_ENV") or "DASHSCOPE_API_KEY"),
            oss_bucket=os.getenv("WEBGAL_OSS_BUCKET") or "ecs-oss-ist",
            oss_endpoint=(os.getenv("WEBGAL_OSS_ENDPOINT") or "https://oss-cn-hangzhou.aliyuncs.com").rstrip("/"),
            oss_access_key_id=os.getenv("OSS_ACCESS_KEY_ID"),
            oss_access_key_secret=os.getenv("OSS_ACCESS_KEY_SECRET"),
            oss_prefix=(os.getenv("WEBGAL_OSS_PREFIX") or "game_assets/public_assets").strip("/"),
            oss_access_mode=(os.getenv("WEBGAL_OSS_ACCESS_MODE") or "public").strip().lower(),
            oss_signed_url_ttl=max(60, int(os.getenv("WEBGAL_OSS_SIGNED_URL_TTL", "900"))),
            database_url=os.getenv("NARRATIVEOS_DATABASE_URL") or os.getenv("DATABASE_URL"),
            asset_library_enabled=(os.getenv("WEBGAL_ASSET_LIBRARY_ENABLED") or "false").strip().lower() in {"1", "true", "yes", "on"},
            database_job_store_enabled=(os.getenv("WEBGAL_DATABASE_JOB_STORE_ENABLED") or "false").strip().lower() in {"1", "true", "yes", "on"},
        )


settings = Settings.from_env()
