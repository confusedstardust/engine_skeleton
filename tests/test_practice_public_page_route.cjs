const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");

async function main() {
  // Exercise the actual production Next server, not only mock FastAPI routes.
  const port = "3367";
  const base = `http://127.0.0.1:${port}/narrativeos/practice/works/${"a".repeat(32)}`;
  const server = spawn(process.execPath, [
    "node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1",
    "--port", port,
  ], { cwd: process.cwd(), env: {
    ...process.env, NEXT_PUBLIC_BASE_PATH: "/narrativeos",
    FORGE_BACKEND_URL: "http://127.0.0.1:8010",
  }, stdio: ["ignore", "pipe", "pipe"] });
  let logs = "";
  server.stdout.on("data", chunk => { logs += chunk.toString(); });
  server.stderr.on("data", chunk => { logs += chunk.toString(); });
  const sleep = millis => new Promise(resolve => setTimeout(resolve, millis));
  try {
    let ready = false;
    const observed = [];
    for (let i = 0; i < 60; i++) {
      if (server.exitCode != null) break;
      try {
        const res = await fetch(base + "/", { signal: AbortSignal.timeout(1200), redirect: "manual" });
        observed.push(`${res.status} ${res.headers.get("location") || ""}`);
        if (res.status === 200) { ready = true; break; }
      } catch { /* Start up is still in progress. */ }
      await sleep(400);
    }
    assert.ok(ready, `Public route not accessible from Next production server. responses=${observed.slice(-8).join(",")} logs=${logs.slice(-2000)}`);
    const canonical = await fetch(base + "/");
    assert.equal(canonical.status, 200, "Canonical published work URL must serve the viewer");
    const legacy = await fetch(base, { redirect: "follow" });
    assert.equal(legacy.status, 200, "Previously shared slashless URL must still open");
    assert.equal(new URL(legacy.url).pathname, `/narrativeos/practice/works/${"a".repeat(32)}/`);
    console.log("Public work route and legacy redirect: OK");
  } finally {
    server.kill("SIGTERM");
    await sleep(350);
    if (server.exitCode === null) server.kill("SIGKILL");
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
