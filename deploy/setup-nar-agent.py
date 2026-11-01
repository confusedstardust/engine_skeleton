"""Run ON THE SERVER from its Compose deployment directory, after image build.

Only creates private Agent env files and a root service token. Does not start
containers, change existing application keys, or print any credential.
"""
import argparse
import getpass
import os
import re
import secrets
from pathlib import Path


def read_env(path):
    result = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                result[key.strip()] = value.strip().strip("\"'")
    return result


def write_private(path, values):
    temporary = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        for key, value in values.items():
            if any(char in value for char in "\r\n'"):
                raise ValueError("Unsupported env value")
            file.write(f"{key}='{value}'\n")
    temporary.replace(path)
    os.chmod(path, 0o600)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", choices=["production", "development"], default="production")
    parser.add_argument("--enable", action="store_true", help="Enable optional Agent overlay on the next full CI deployment")
    args = parser.parse_args()
    root = Path.cwd()
    compose_file = "docker-compose.dev.yml" if args.environment == "development" else "docker-compose.prod.yml"
    if not (root / compose_file).exists() or not (root / ".env").exists():
        raise SystemExit(f"Run from the {args.environment} directory containing {compose_file} and .env")
    root_env = read_env(root / ".env")
    target = root / "deploy"
    target.mkdir(exist_ok=True)
    current = read_env(target / "nar-agent.env")
    configured_environment = current.get("NAR_AGENT_DEPLOYMENT_ENV")
    if configured_environment and configured_environment != args.environment:
        raise SystemExit("Refusing to overwrite credentials from another deployment environment")
    service = root_env.get("NAR_AGENT_SERVICE_TOKEN") or secrets.token_urlsafe(48)
    execution = current.get("NAR_AGENT_EXECUTION_TOKEN") or secrets.token_urlsafe(48)
    if service.startswith("replace-with-"):
        service = secrets.token_urlsafe(48)
    if execution.startswith("replace-with-"):
        execution = secrets.token_urlsafe(48)
    key = current.get("NAR_AGENT_API_KEY") or getpass.getpass("Agent model API key (hidden input): ").strip()
    if not key or len(service) < 32 or len(execution) < 32:
        raise SystemExit("Missing model key or invalid service credential")
    write_private(target / "nar-agent.env", {
        "NAR_AGENT_DEPLOYMENT_ENV": args.environment,
        "NAR_AGENT_SERVICE_TOKEN": service, "NAR_AGENT_EXECUTION_TOKEN": execution,
        "NAR_AGENT_API_KEY": key, "NAR_AGENT_MODEL": current.get("NAR_AGENT_MODEL", "deepseek-chat"),
        "NAR_AGENT_BASE_URL": current.get("NAR_AGENT_BASE_URL", "https://api.deepseek.com"),
        "NAR_AGENT_MAX_CONCURRENT_RUNS": "1", "NAR_AGENT_ANIMATION_TIMEOUT_SECONDS": "600",
    })
    write_private(target / "nar-execution.env", {"NAR_EXECUTION_TOKEN": execution, "NAR_AGENT_DEPLOYMENT_ENV": args.environment})
    path = root / ".env"
    text = path.read_text(encoding="utf-8")
    line = "NAR_AGENT_SERVICE_TOKEN='" + service + "'"
    text = re.sub(r"(?m)^NAR_AGENT_SERVICE_TOKEN=.*$", line, text) if "NAR_AGENT_SERVICE_TOKEN" in root_env else text.rstrip() + "\n" + line + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_TRUNC)
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        file.write(text)
    if args.enable:
        (root / ".nar-agent-enabled").touch(mode=0o600)
    print("Private Agent configuration saved. No credentials printed. Containers have not been changed.")
    print(f"Run a full {args.environment} deployment to apply; real Docker smoke must pass first.")


if __name__ == "__main__":
    main()
