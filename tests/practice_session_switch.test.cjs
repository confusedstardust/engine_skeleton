const test = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync, existsSync } = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const file = name => readFileSync(path.join(root, name), "utf8");
const base = "forge_frontend_next/app/practice/";

test("NarAgent chat never persists or restores messages using browser storage", () => {
  assert.equal(existsSync(path.join(root, base + "practice-session.ts")), false,
    "obsolete sessionStorage module must be removed");
  for (const path of [
    base + "use-practice-workspace.ts",
    base + "use-nar-conversation.ts",
    base + "practice-types.ts",
    base + "practice-navigation.tsx",
    "forge_frontend_next/lib/conversation-api.ts",
  ]) {
    const source = file(path);
    assert.doesNotMatch(source, /\bsessionStorage\b|readPracticeSession|writePracticeSession|recoverPracticeSession|clearPracticeSession|PendingCreation/);
  }
});

test("every new prompt uses the logged-in user's durable Forge conversation endpoint", () => {
  const hook = file(base + "use-practice-workspace.ts");
  const client = file("forge_frontend_next/lib/conversation-api.ts");
  const server = file(base + "use-nar-conversation.ts");
  const chat = file(base + "practice-chat.tsx");
  assert.match(hook, /await server\.send\(prompt, "auto", parent\)/);
  assert.doesNotMatch(hook, /\bforgeApi<ChatReply>|followBuildTask|nar-agent\/html|nar-agent\/chat|nar-agent\/animations/);
  assert.match(server, /conversationApi\.status\(\)/);
  assert.match(server, /conversationApi\.stream\(/);
  assert.match(server, /setLiveReply\(ownerId, targetId, text\)/);
  assert.match(client, /text\/event-stream/);
  assert.match(server, /conversationApi\.get\(conversationId\)/);
  assert.match(client, /\/conversations\/status/);
  assert.match(client, /\/conversations/);
  assert.match(chat, /serverReady && loggedIn/);
  assert.doesNotMatch(server, /NAR_CONVERSATIONS_ENABLED/);
});

test("query changes isolate React state; saved work deep links load only owner-checked HTML", () => {
  const layout = file(base + "layout.tsx");
  const dynamic = file(base + "chat/[conversationId]/page.tsx");
  const hook = file(base + "use-practice-workspace.ts");
  assert.match(layout, /useSearchParams\(\)/);
  assert.match(layout, /<PracticeShell workspaceScope=\{workspaceScope\}/);
  assert.doesNotMatch(layout, /<PracticeShell key=/);
  assert.match(dynamic, /return null/);
  assert.match(hook, /loadSavedWork\(workspaceScope\)/);
  assert.match(hook, /router\.push\("\/practice\/"\)/);
  assert.doesNotMatch(hook, /sessionUserId, \{\s*messages/);
});

test("loading icon and plaza-style full viewport sidebar reuse shared controls", () => {
  const chat = file(base + "practice-chat.tsx");
  const side = file("forge_frontend_next/components/ui/workspace-sidebar.module.css");
  const studio = file(base + "practice.module.css");
  assert.match(chat, /import \{ LoadingState \} from "\.\.\/\.\.\/components\/ui\/state"/);
  assert.doesNotMatch(chat, /className=\{styles\.runningRow\}/);
  assert.match(chat, /streamText && <article/);
  const history = file(base + "practice-history-list.tsx");
  assert.match(history, /navBookWorking/);
  assert.match(side, /border-right:1px solid/);
  assert.match(side, /border-radius:0/);
  assert.match(studio, /\.layout \.sidebar\{position:fixed!important;inset:0 auto 0 0;z-index:120/);
});
