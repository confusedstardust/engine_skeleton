"""Configure ignored local dotenv files without printing credentials."""
import secrets
from pathlib import Path

from dotenv import dotenv_values, set_key

root = Path(__file__).resolve().parents[1]
forge_path = root / ".env"
agent_path = root / "nar_agent" / ".env"
forge = dotenv_values(forge_path)
if not forge_path.exists():
    raise SystemExit("Create the root .env from .env.example first.")
if not agent_path.exists():
    agent_path.write_text((agent_path.parent / ".env.example").read_text(encoding="utf-8"), encoding="utf-8")
agent = dotenv_values(agent_path)
token = forge.get("NAR_AGENT_SERVICE_TOKEN") or agent.get("NAR_AGENT_SERVICE_TOKEN") or ""
if len(token) < 32 or token.startswith("replace-with-"):
    token = secrets.token_urlsafe(48)
set_key(str(forge_path), "NAR_AGENT_SERVICE_TOKEN", token)
set_key(str(forge_path), "NAR_AGENT_URL", "http://127.0.0.1:8020")
set_key(str(agent_path), "NAR_AGENT_SERVICE_TOKEN", token)
key = agent.get("NAR_AGENT_API_KEY")
if not key or key.startswith("your-"):
    key = forge.get("DEEPSEEK_API_KEY")
    if not key or key.startswith("your-"):
        raise SystemExit("Set NAR_AGENT_API_KEY in nar_agent/.env; no usable local DeepSeek key found.")
    set_key(str(agent_path), "NAR_AGENT_API_KEY", key)
    set_key(str(agent_path), "NAR_AGENT_BASE_URL", forge.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com")
    set_key(str(agent_path), "NAR_AGENT_MODEL", "deepseek-chat")
print("Local NarAgent configured. Service tokens match; credentials were not displayed.")
print("Local model key reuses the existing DeepSeek key if NarAgent had no key. Use a separate key for production.")
