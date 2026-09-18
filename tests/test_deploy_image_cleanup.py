from datetime import datetime, timezone
from pathlib import Path
import os
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/deploy_cleanup_images.sh"
COMPLETED = 1900000000


def run_cleanup(inspect_failure=False):
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    bash = str(git_bash) if git_bash.exists() else shutil.which("bash")
    if not bash:
        pytest.skip("Bash unavailable")
    old = datetime.fromtimestamp(COMPLETED - 108001, timezone.utc).isoformat()
    boundary = datetime.fromtimestamp(COMPLETED - 108000, timezone.utc).isoformat()
    harness = r'''
docker() {
  case "$1 $2" in
    "image ls")
      case "$4" in
        reference=registry/backend:*) printf 'registry/backend old\nregistry/backend used\nregistry/backend boundary\nregistry/other ancient\nregistry/backend <none>\n' ;;
        reference=registry/frontend:*) printf 'registry/frontend old\nregistry/frontend recent\n' ;;
        *) return 9 ;;
      esac ;;
    "image inspect")
      if [ "$FAIL_INSPECT" = "true" ]; then return 1; fi
      if [ "$4" = '{{.Id}}' ]; then printf '%s\n' "$5";
      else
        case "$5" in
          *:boundary|*:recent) printf '%s\n' "$BOUNDARY" ;;
          *) printf '%s\n' "$OLD" ;;
        esac
      fi ;;
    "ps --all")
      case "$5" in ancestor=registry/backend:used) echo stopped-container ;; esac ;;
    "image rm")
      [ "$3" = "--no-prune" ] || return 8
      printf 'REMOVED %s\n' "$4" ;;
    *) return 7 ;;
  esac
}
export -f docker
export OLD BOUNDARY FAIL_INSPECT
bash "$1" registry/backend registry/frontend "$2"
'''
    env = dict(os.environ, OLD=old, BOUNDARY=boundary, FAIL_INSPECT=str(inspect_failure).lower())
    return subprocess.run([bash, "-c", harness, "cleanup-test", SCRIPT.as_posix(), str(COMPLETED)], env=env, capture_output=True, text=True)


def test_cleanup_age_scope_boundary_and_stopped_container_protection():
    result = run_cleanup()
    assert result.returncode == 0, result.stderr
    removed = [line for line in result.stdout.splitlines() if line.startswith("REMOVED ")]
    assert removed == ["REMOVED registry/backend:old", "REMOVED registry/frontend:old"]
    assert "Keep container-referenced image: registry/backend:used" in result.stdout
    assert "Keep recent image: registry/backend:boundary" in result.stdout


def test_inspection_failure_never_deletes_images():
    result = run_cleanup(inspect_failure=True)
    assert result.returncode != 0
    assert "REMOVED " not in result.stdout


def test_workflow_uploads_script_and_cleans_after_recreation():
    yaml = pytest.importorskip("yaml")
    data = yaml.safe_load((ROOT / ".github/workflows/docker-publish-deploy.yml").read_text(encoding="utf-8"))
    steps = data["jobs"]["deploy"]["steps"]
    upload = next(step for step in steps if step["name"] == "Upload deployment files")
    assert "scripts/deploy_cleanup_images.sh" in upload["with"]["source"]
    script = next(step for step in steps if step["name"] == "Deploy on remote host")["with"]["script"]
    assert script.index("Finished post-deployment backend recreation") < script.index('DEPLOY_COMPLETED_AT=') < script.index('/scripts/deploy_cleanup_images.sh')
    assert "docker system prune" not in script
    assert "docker image prune" not in script
