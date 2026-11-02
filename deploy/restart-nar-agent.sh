#!/usr/bin/env bash
# Upload beside docker-compose.dev.yml (or into its deploy/ directory).
# Default: development. Production requires --environment production.
set -Eeuo pipefail

ENVIRONMENT=development
while (($#)); do
  case "$1" in
    --environment)
      ENVIRONMENT="${2:?Missing environment: development or production}"
      shift 2 ;;
    -h|--help)
      echo "Usage: bash restart-nar-agent.sh [--environment development|production]"
      exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done
case "$ENVIRONMENT" in
  development) BASE=docker-compose.dev.yml ;;
  production) BASE=docker-compose.prod.yml ;;
  *) echo 'Environment must be development or production.' >&2; exit 1 ;;
esac

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
if [[ -f "$HERE/$BASE" ]]; then
  ROOT=$HERE
elif [[ -f "$HERE/../$BASE" ]]; then
  ROOT=$(cd -- "$HERE/.." && pwd -P)
else
  echo "Cannot find $BASE beside the script or in its parent directory." >&2
  echo 'Upload to the DEV deployment directory. For production, explicitly use --environment production.' >&2
  exit 1
fi
cd -- "$ROOT"
for file in .env .deploy-images.env docker-compose.nar-agent.yml deploy/nar-agent.env deploy/nar-execution.env; do
  if [[ ! -s "$file" ]]; then
    echo "Missing configuration: $file" >&2
    echo "First run in this directory: python3 deploy/setup-nar-agent.py --environment $ENVIRONMENT --enable" >&2
    echo 'Image pins and Compose files are supplied by the matching CI deployment.' >&2
    exit 1
  fi
done

# Parse only image references, never execute/source arbitrary dotenv contents.
unset BACKEND_IMAGE FRONTEND_IMAGE NAR_AGENT_IMAGE NAR_EXECUTION_IMAGE NAR_SANDBOX_IMAGE
while IFS= read -r line || [[ -n "$line" ]]; do
  line=${line%$'\r'}
  key=${line%%=*}
  case "$key" in
    BACKEND_IMAGE|FRONTEND_IMAGE|NAR_AGENT_IMAGE|NAR_EXECUTION_IMAGE|NAR_SANDBOX_IMAGE)
      value=${line#*=}
      value=${value#\'}; value=${value%\'}
      value=${value#\"}; value=${value%\"}
      if [[ ! "$value" =~ ^[[:alnum:]][[:alnum:]_.:/@-]*$ ]]; then
        echo "Invalid image pin for $key" >&2; exit 1
      fi
      export "$key=$value" ;;
  esac
done < .deploy-images.env
for key in BACKEND_IMAGE FRONTEND_IMAGE NAR_AGENT_IMAGE NAR_EXECUTION_IMAGE NAR_SANDBOX_IMAGE; do
  [[ -n "${!key:-}" ]] || { echo "Missing image pin: $key. Run a full CI build first." >&2; exit 1; }
  if [[ "$ENVIRONMENT" == development && "${!key}" != *:dev-sha-* ]]; then
    echo "Refusing non-development image pin: $key" >&2; exit 1
  fi
done

# Validate private files without displaying their values. Prefer the .env token
# rather than any stale interactive-shell override during Compose interpolation.
unset NAR_AGENT_SERVICE_TOKEN
python3 - "$ENVIRONMENT" <<'PY'
import sys
from pathlib import Path
def read(path):
    values = {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip().strip("\"'")
    return values
root = read('.env')
agent = read('deploy/nar-agent.env')
execution = read('deploy/nar-execution.env')
def require(ok, message):
    if not ok: raise SystemExit(message)
require(agent.get('NAR_AGENT_DEPLOYMENT_ENV') == sys.argv[1], 'Agent environment mismatch. Run the matching setup script first.')
require(execution.get('NAR_AGENT_DEPLOYMENT_ENV') == sys.argv[1], 'Execution environment mismatch. Run the matching setup script first.')
for name, value in [('service', agent.get('NAR_AGENT_SERVICE_TOKEN', '')), ('execution', agent.get('NAR_AGENT_EXECUTION_TOKEN', ''))]:
    require(len(value) >= 32 and not value.startswith('replace-with-'), name + ' token is not configured.')
require(root.get('NAR_AGENT_SERVICE_TOKEN') == agent['NAR_AGENT_SERVICE_TOKEN'], 'Forge/Agent service tokens do not match.')
require(execution.get('NAR_EXECUTION_TOKEN') == agent['NAR_AGENT_EXECUTION_TOKEN'], 'Agent/execution tokens do not match.')
require(bool(agent.get('NAR_AGENT_API_KEY')), 'Agent model API key is missing.')
print('Private configuration validated; credentials not displayed.')
PY

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  echo 'Docker Compose is not installed.' >&2; exit 1
fi
compose() {
  "${COMPOSE[@]}" --project-directory "$ROOT" --env-file "$ROOT/.env" \
    -f "$ROOT/$BASE" -f "$ROOT/docker-compose.nar-agent.yml" "$@"
}
compose config --quiet
echo "Environment: $ENVIRONMENT"
echo "Deployment directory: $ROOT"
echo 'Preparing images...'
for image in "$NAR_SANDBOX_IMAGE" "$NAR_EXECUTION_IMAGE" "$NAR_AGENT_IMAGE" "$BACKEND_IMAGE"; do
  docker image inspect "$image" >/dev/null 2>&1 || docker pull "$image"
done
wait_ready() {
  local service=$1 python=$2 url=$3
  for ((attempt=1; attempt<=20; attempt++)); do
    if compose exec -T "$service" "$python" -c "import urllib.request; urllib.request.urlopen('$url', timeout=3)" >/dev/null 2>&1; then
      echo "$service is ready."
      return 0
    fi
    sleep 3
  done
  echo "$service did not become ready. Check its container logs." >&2
  compose ps
  return 1
}

echo 'Recreating execution service...'
compose up -d --no-deps --force-recreate execution
wait_ready execution python http://127.0.0.1:8030/ready
echo 'Recreating NarAgent...'
compose up -d --no-deps --force-recreate nar-agent
wait_ready nar-agent .venv/bin/python http://127.0.0.1:8020/ready
echo 'Recreating backend to apply the Agent connection settings...'
compose up -d --no-deps --force-recreate backend
wait_ready backend python http://127.0.0.1:8010/health
compose exec -T backend python - <<'PY'
import os
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler
opener = build_opener(ProxyHandler({}))
request = Request(os.environ['NAR_AGENT_URL'].rstrip('/') + '/v1/animations/' + '0' * 32,
                  headers={'Authorization': 'Bearer ' + os.environ['NAR_AGENT_SERVICE_TOKEN'], 'X-User-ID': 'restart-readiness'})
try:
    opener.open(request, timeout=5)
except HTTPError as error:
    if error.code != 404: raise SystemExit('Service authentication failed: HTTP ' + str(error.code))
else:
    raise SystemExit('Unexpected task response during authentication check')
print('Backend -> NarAgent authentication passed; no model invocation.')
PY
compose ps
echo 'Done. Open the teaching tools page to test the Agent.'
