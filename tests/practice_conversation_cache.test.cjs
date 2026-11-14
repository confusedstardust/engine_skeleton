const test = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const read = name => readFileSync(path.join(root, name), "utf8");

function loadTs(relative) {
  const ts = require("../forge_frontend_next/node_modules/typescript");
  const js = ts.transpileModule(read(relative), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const exports = {};
  vm.runInNewContext(js, { exports, Date, Map, Set, Promise, console, Error }, { filename: relative });
  return exports;
}

test("duplicate same-owner requests share one in-flight fetch; a fresh route remount uses cache", async () => {
  const c = loadTs("forge_frontend_next/lib/conversation-query-cache.ts");
  let requests = 0;
  let complete;
  const fetcher = () => {
    requests++;
    return new Promise(resolve => { complete = resolve; });
  };
  const a = c.getConversationQuery("teacher-A", "detail:abc", 120000, fetcher);
  const b = c.getConversationQuery("teacher-A", "detail:abc", 120000, fetcher);
  assert.equal(requests, 1);
  complete({ conversation: { id: "abc" }, messages: ["from server"] });
  const [resultA, resultB] = await Promise.all([a, b]);
  assert.deepEqual(resultA.messages, ["from server"]);
  assert.deepEqual(resultB.messages, ["from server"]);
  const cached = await c.getConversationQuery("teacher-A", "detail:abc", 120000,
    () => { requests++; throw Error("must not refetch fresh detail"); });
  assert.equal(requests, 1);
  assert.deepEqual(cached.messages, ["from server"]);
  assert.equal(c.peekConversationQuery("teacher-B", "detail:abc"), undefined);
});

test("mutations update only the relevant sidebar list without firing a new network request", async () => {
  const c = loadTs("forge_frontend_next/lib/conversation-query-cache.ts");
  c.setConversationQuery("owner", "list", { items: [], nextCursor: null });
  let notifications = 0;
  const off = c.subscribeConversationQuery("owner", "list", () => { notifications++; });
  c.upsertConversationSummary("owner", { id: "first", title: "串并联电路实验" });
  assert.equal(notifications, 1);
  assert.equal(c.peekConversationQuery("owner", "list").items[0].title, "串并联电路实验");
  const again = await c.getConversationQuery("owner", "list", 60000, () => {
    throw Error("no fetch allowed");
  });
  assert.equal(again.items.length, 1);
  c.invalidateConversationQuery("owner", "artifacts");
  assert.equal(notifications, 1);
  off();
});

test("cached replies include no browser-persistent chat or focus-list reload", () => {
  const nav = read("forge_frontend_next/app/practice/practice-navigation.tsx");
  const layout = read("forge_frontend_next/app/practice/layout.tsx");
  const hook = read("forge_frontend_next/app/practice/use-nar-conversation.ts");
  const cache = read("forge_frontend_next/lib/conversation-query-cache.ts");
  assert.doesNotMatch(nav, /addEventListener\("focus"|focusEpoch|serverRevision/);
  assert.match(nav, /CONVERSATION_STALE_MS.list/);
  assert.match(hook, /CONVERSATION_STALE_MS.detail/);
  assert.match(layout, /Intentionally no key/);
  assert.doesNotMatch(cache, /sessionStorage|localStorage|indexedDB/);
});

test("task errors display the public agent reason and safe phase/code, not a generic retry hint", () => {
  const { formatPracticeFailure } = loadTs("forge_frontend_next/app/practice/practice-failure.ts");
  const result = formatPracticeFailure(
    { status: "FAILED", errorCode: "AGENT_ERROR", runId: "16696fa0c1fc404fbeb26c9101291bcd" },
    { id: "16696fa0c1fc404fbeb26c9101291bcd", error: "HTML 制作失败，请检查执行服务或稍后重试。",
      error_code: "AGENT_ERROR", phase: "DESIGNING" },
  );
  assert.match(result, /HTML 制作失败/);
  assert.match(result, /AGENT_ERROR/);
  assert.match(result, /DESIGNING/);
  assert.match(result, /16696fa0c1fc404fbeb26c9101291bcd/);
  assert.doesNotMatch(result, /上次创作未完成/);
});
