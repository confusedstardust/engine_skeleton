"""Configuration isolation is exercised with fake files/keys, never server creds."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy/setup-nar-agent.py"


def prepare(root, environment):
    root.mkdir()
    filename = "docker-compose.dev.yml" if environment == "development" else "docker-compose.prod.yml"
    (root / filename).write_text("services: {}\n")
    (root / ".env").write_text("UNRELATED_SETTING='keep-me'\n")
    (root / "deploy").mkdir()
    (root / "deploy/nar-agent.env").write_text("NAR_AGENT_API_KEY='fake-test-provider-key'\n")


def invoke(root, environment):
    return subprocess.run([sys.executable, str(SCRIPT), "--environment", environment, "--enable"], cwd=root, capture_output=True, text=True, timeout=10)


def values(path):
    return {line.split("=", 1)[0]: line.split("=", 1)[1].strip("'") for line in path.read_text().splitlines() if "=" in line}


def test_dev_and_prod_setup_have_independent_credentials(tmp_path):
    records = []
    for environment in ["development", "production"]:
        root = tmp_path / environment
        prepare(root, environment)
        result = invoke(root, environment)
        assert result.returncode == 0, result.stderr
        assert "fake-test-provider-key" not in result.stdout
        assert (root / ".nar-agent-enabled").exists()
        agent = values(root / "deploy/nar-agent.env")
        execution = values(root / "deploy/nar-execution.env")
        assert agent["NAR_AGENT_DEPLOYMENT_ENV"] == environment
        assert execution["NAR_AGENT_DEPLOYMENT_ENV"] == environment
        assert agent["NAR_AGENT_EXECUTION_TOKEN"] == execution["NAR_EXECUTION_TOKEN"]
        assert agent["NAR_AGENT_SERVICE_TOKEN"] == values(root / ".env")["NAR_AGENT_SERVICE_TOKEN"]
        assert values(root / ".env")["UNRELATED_SETTING"] == "keep-me"
        records.append(agent)
    assert records[0]["NAR_AGENT_SERVICE_TOKEN"] != records[1]["NAR_AGENT_SERVICE_TOKEN"]
    assert records[0]["NAR_AGENT_EXECUTION_TOKEN"] != records[1]["NAR_AGENT_EXECUTION_TOKEN"]


def test_dev_setup_rejects_production_directory_and_existing_credentials(tmp_path):
    root = tmp_path / "production"
    prepare(root, "production")
    before = (root / ".env").read_bytes()
    assert invoke(root, "development").returncode != 0
    assert (root / ".env").read_bytes() == before
    assert not (root / ".nar-agent-enabled").exists()
    assert invoke(root, "production").returncode == 0
    (root / "docker-compose.dev.yml").write_text("services: {}\n")
    before = (root / "deploy/nar-agent.env").read_bytes()
    assert invoke(root, "development").returncode != 0
    assert (root / "deploy/nar-agent.env").read_bytes() == before


def test_credential_healthcheck_uses_no_model_call(tmp_path):
    import os
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/ready": self.send_response(200)
            elif self.path.startswith("/v1/animations/") and self.headers.get("Authorization") == "Bearer fake-token": self.send_response(404)
            else: self.send_response(401)
            self.end_headers()
        def log_message(self, *args): pass
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        env = {**os.environ, "NAR_AGENT_URL": f"http://127.0.0.1:{server.server_port}", "NAR_AGENT_SERVICE_TOKEN": "fake-token"}
        result = subprocess.run([sys.executable, str(ROOT / "deploy/nar-agent-healthcheck.py")], env=env, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
        env["NAR_AGENT_SERVICE_TOKEN"] = "wrong-token"
        result = subprocess.run([sys.executable, str(ROOT / "deploy/nar-agent-healthcheck.py")], env=env, capture_output=True, text=True, timeout=10)
        assert result.returncode != 0
        assert "wrong-token" not in result.stdout + result.stderr
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
