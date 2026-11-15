const test = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const read = name => readFileSync(path.resolve(__dirname, "..", name), "utf8");
const practice = "forge_frontend_next/app/practice/";

test("plaza sidebar covers header and footer with graceful width animation", () => {
  const css = read(practice + "practice.module.css");
  const navCss = read("forge_frontend_next/components/ui/workspace-sidebar.module.css");
  const resize = read(practice + "resizable-workspace.tsx");
  assert.match(css, /position:fixed!important;inset:0 auto 0 0;z-index:120/);
  assert.match(css, /height:100dvh!important/);
  assert.match(css, /top-nav/);
  assert.match(css, /workspace-nav-leading/);
  assert.match(resize, /styles.navPlaceholder/);
  assert.match(navCss, /transition:width 280ms/);
  assert.match(navCss, /prefers-reduced-motion:reduce/);
  assert.match(navCss, /root\[data-collapsed=true\] \.itemLabel/);
  assert.match(resize, /navCollapsed/);
});

test("history routes reuse one practice shell, and URLs carry conversation identity", () => {
  const shell = read(practice + "practice-shell.tsx");
  const layout = read(practice + "layout.tsx");
  const dynamic = read(practice + "chat/[conversationId]/page.tsx");
  const hook = read(practice + "use-practice-workspace.ts");
  const nav = read(practice + "practice-navigation.tsx");
  assert.match(shell, /usePracticeWorkspace\(workspaceScope, conversationId\)/);
  assert.match(layout, /<PracticeShell workspaceScope=\{workspaceScope\}/);
  assert.match(dynamic, /return null/);
  assert.match(hook, /useNarConversation/);
  assert.match(nav, /getConversationQuery\(ownerId, "list"/);
  assert.match(nav, /conversationApi\.artifacts\(\)/);
  assert.match(read(practice + "practice-history-list.tsx"), /\/practice\/chat\//);
  assert.match(nav, /aria-selected=\{view === "conversations"\}/);
});

test("persistent chat uses authenticated APIs without a runtime feature flag", () => {
  const route = read("webgal_backend/nar_conversation_routes.py");
  const migration = read("webgal_backend/migrations/002_nar_conversation_history.sql");
  const app = read("webgal_backend/app.py");
  assert.doesNotMatch(route, /NAR_CONVERSATIONS_ENABLED/);
  assert.doesNotMatch(read(practice + "use-practice-workspace.ts"), /sessionStorage|recoverPracticeSession/);
  assert.match(route, /async def owner_for/);
  assert.match(route, /"ready": True/);
  assert.match(route, /if not await run_in_threadpool\(ledger\.ready\)/);
  assert.match(route, /auth_type/);
  assert.match(route, /client_request_id/);
  assert.match(route, /reused.*True/);
  assert.match(route, /UNCERTAIN/);
  assert.match(app, /create_nar_conversation_router/);
  assert.doesNotMatch(route, /CREATE TABLE|ALTER TABLE|DROP TABLE/);
  for (const table of [
    "nar_conversations", "nar_messages", "nar_turns",
    "nar_turn_dispatches", "nar_conversation_artifacts",
  ]) assert.match(migration, new RegExp("CREATE TABLE IF NOT EXISTS " + table));
  assert.match(migration, /uq_nar_turns_idempotency/);
  assert.match(migration, /idx_nar_conversations_owner_active/);
});

test("work preview stays owner-scoped and server lists do not fetch HTML eagerly", () => {
  const api = read("forge_frontend_next/lib/conversation-api.ts");
  const projection = read(practice + "practice-conversation.ts");
  const hook = read(practice + "use-nar-conversation.ts");
  assert.match(read("forge_frontend_next/lib/api-client.ts"), /credentials: "include"/); // existing shared gateway
  assert.match(api, /\/artifact-history/);
  assert.match(projection, /loadSavedWork/);
  assert.match(projection, /forgeApi\.blob/);
  assert.match(hook, /conversationApi\.associateWork/);
  assert.match(hook, /crypto\.getRandomValues/);
});
