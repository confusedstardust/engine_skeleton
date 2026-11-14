const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const read = file => fs.readFileSync(path.join(__dirname, "..", file), "utf8");

test("execution healthcheck is cheap liveness, not a Docker-engine image probe", () => {
  const compose = read("docker-compose.nar-agent.yml");
  const execution = compose.split("\n  execution:\n")[1];
  assert.ok(execution, "execution service must be defined");
  assert.match(execution, /8030\/health/);
  assert.doesNotMatch(execution.split("\nvolumes:\n")[0], /8030\/ready/);
  assert.match(execution, /start_period: 40s/);
  const broker = read("nar_agent/sandbox/broker.py");
  assert.match(broker, /@app.get\("\/ready"\)/);
  assert.match(broker, /client\.ping\(\)/);
  assert.match(broker, /client\.images\.get\(os\.environ\["NAR_SANDBOX_IMAGE"\]\)/);
});

test("DEV deployment waits for real execution readiness before starting NarAgent", () => {
  const workflow = read(".github/workflows/docker-publish-deploy-dev.yml");
  const start = workflow.indexOf("up -d --no-deps execution");
  const ready = workflow.indexOf("EXECUTION_READY=false", start);
  const check = workflow.indexOf("8030/ready", ready);
  const gate = workflow.indexOf('if [ "$EXECUTION_READY" != "true" ]; then', check);
  const startAgent = workflow.indexOf("up -d nar-agent", gate);
  assert.ok(start >= 0 && ready > start && check > ready && gate > check && startAgent > gate,
    "real /ready must gate NarAgent creation");
  assert.match(workflow, /timeout 20s \$COMPOSE_CMD/);
  assert.match(workflow, /attempt \$attempt\/12/);
  assert.match(workflow, /docker inspect "\$EXECUTION_CONTAINER"/);
  assert.match(workflow, /exit 1\s+fi\s+\$COMPOSE_CMD --env-file \.env \$COMPOSE_FILES up -d nar-agent/);
});

test("changes remain limited to development deployment, not prod job", () => {
  const workflow = read(".github/workflows/docker-publish-deploy-dev.yml");
  assert.match(workflow, /name: docker-publish-deploy-development/);
  assert.doesNotMatch(workflow, /name: docker-publish-deploy-production/);
});


test("push path-filter detects current changes instead of diffing feature against main", () => {
  const workflow = read(".github/workflows/docker-publish-deploy-dev.yml");
  assert.match(workflow, /uses: dorny\/paths-filter@v3[\s\S]*?base: \$\{\{ github\.ref \}\}/);
  assert.match(workflow, /nar_agent:\s*\n\s+- 'nar_agent\/\*\*'/);
});
