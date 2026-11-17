const { test } = require("node:test");
const assert = require("node:assert/strict");
const { pathToFileURL } = require("node:url");
const path = require("node:path");

test("Next proxy exposes both private and public work endpoints", async () => {
  const filename = path.join(__dirname, "../forge_frontend_next/next.config.mjs");
  const { default: config } = await import(pathToFileURL(filename).href);
  const rewrites = await config.rewrites();
  for (const [route, destination] of [
    ["/api/forge/works", "/works"],
    ["/api/forge/works/:path*", "/works/:path*"],
    ["/api/forge/public/works", "/public/works"],
    ["/api/forge/public/works/:path*", "/public/works/:path*"],
  ]) {
    const matching = rewrites.filter(rewrite => rewrite.source === route);
    assert.equal(matching.length, 1, `Missing/duplicate work route: ${route}`);
    assert.ok(matching[0].destination.endsWith(destination), `Wrong proxy destination for ${route}`);
  }
  // Public snapshots must not be mapped to the owner-only private work endpoint.
  assert.notEqual(
    rewrites.find(rewrite => rewrite.source === "/api/forge/public/works/:path*").destination,
    rewrites.find(rewrite => rewrite.source === "/api/forge/works/:path*").destination,
  );
});
