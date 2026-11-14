from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NAR_AGENT_", env_file=".env", extra="ignore")

    service_token: SecretStr = SecretStr("")
    api_key: SecretStr = SecretStr("")
    model: str = "deepseek-flash"
    base_url: str = "https://api.deepseek.com"
    timeout_seconds: float = Field(default=120, gt=0, le=600)
    max_output_tokens: int = Field(default=2048, ge=128, le=16384)
    recursion_limit: int = Field(default=20, ge=2, le=100)
    max_concurrent_runs: int = Field(default=2, ge=1, le=8)
    animation_enabled: bool = False
    html_builder_enabled: bool = False
    public_brief_enabled: bool = False
    execution_url: str = "http://execution:8030"
    execution_token: SecretStr = SecretStr("")
    artifact_dir: str = "./artifacts"
    animation_timeout_seconds: float = Field(default=600, ge=30, le=900)

    @property
    def ready(self) -> bool:
        token = self.service_token.get_secret_value()
        return len(token) >= 32 and not token.startswith("replace-with-") and bool(self.api_key.get_secret_value())
