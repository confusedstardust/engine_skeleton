const test = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const file = p => fs.readFileSync(path.join(root, p), "utf8");
const base = "forge_frontend_next/app/practice/";

function sessionModule() {
  const ts = require("../forge_frontend_next/node_modules/typescript");
  const compiled = ts.transpileModule(file(base + "practice-session.ts"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const map = new Map();
  const context = {
    exports: {},
    sessionStorage: {
      getItem: key => map.has(key) ? map.get(key) : null,
      setItem: (key, value) => map.set(key, value),
      removeItem: key => map.delete(key),
    },
  };
  vm.runInNewContext(compiled, context, { filename: "practice-session.js" });
  return context.exports;
}
const item = (id, workId) => ({ artifactId: id.repeat(32), workId, kind: "html", title: "test" });
const generated = (content, artifactId) => ({
  role: "assistant", content, work: { artifactId, title: content, version: 1, kind: "html" },
});
const user = content => ({ role: "user", content });
const snapshot = (messages, works) => ({
  messages, works, currentArtifactId: null, selectedArtifactId: null, pending: null,
});

test("workId scopes legacy conversation recovery to exact generated artifact", () => {
  const s = sessionModule();
  const A = item("a", "1".repeat(32));
  const B = item("b", "2".repeat(32));
  const unrelated = user("random question");
  const legacy = [
    user("create A"), generated("result A", A.artifactId),
    unrelated, { role: "assistant", content: "unrelated reply" },
    user("create B"), generated("result B", B.artifactId),
  ];
  s.writePracticeSession("owner", snapshot(legacy, [A, B]), "general");
  const resultA = s.recoverPracticeSession("owner", A.workId);
  const resultB = s.recoverPracticeSession("owner", B.workId);
  assert.deepEqual(Array.from(resultA.messages, m => m.content), ["create A", "result A"]);
  assert.deepEqual(Array.from(resultB.messages, m => m.content), ["create B", "result B"]);
  assert.equal(resultA.works.length, 1);
  assert.equal(resultB.works.length, 1);
  assert.deepEqual(Array.from(s.readPracticeSession("owner", "general").messages, m => m.content),
    legacy.map(m => m.content));
});

test("authoritative work session wins over legacy reconstruction", () => {
  const s = sessionModule();
  const A = item("c", "3".repeat(32));
  s.writePracticeSession("owner", snapshot([user("legacy"), generated("old", A.artifactId)], [A]), "general");
  s.writePracticeSession("owner", snapshot([user("new version"), generated("new", A.artifactId)], [A]), A.workId);
  const recovered = s.recoverPracticeSession("owner", A.workId);
  assert.deepEqual(Array.from(recovered.messages, m => m.content), ["new version", "new"]);
  s.clearPracticeSession("owner", "general");
  assert.equal(s.readPracticeSession("owner", "general"), null);
  assert.ok(s.readPracticeSession("owner", A.workId));
});

test("does not invent old messages when saved work has no traceable transcript", () => {
  const s = sessionModule();
  const A = item("a", "4".repeat(32));
  const B = item("b", "5".repeat(32));
  s.writePracticeSession("owner", snapshot([user("create A"), generated("result A", A.artifactId)], [A, B]), "general");
  assert.equal(s.recoverPracticeSession("owner", B.workId), null);
});

test("App Router remounts work-scoped state and preserves saved chat on new conversation", () => {
  const page = file(base + "page.tsx");
  const hook = file(base + "use-practice-workspace.ts");
  const navigation = file(base + "practice-navigation.tsx");
  assert.match(page, /useSearchParams\(\)/);
  assert.match(page, /<PracticeWorkspace key=\{workspaceScope\}/);
  assert.match(hook, /recoverPracticeSession\(sessionUserId, workspaceScope\)/);
  assert.match(hook, /loadSavedWork\(workspaceScope\)/);
  assert.match(hook, /router\.push\("\/practice\/"\)/);
  assert.match(hook, /clearPracticeSession\(sessionUserId, "general"\)/);
  assert.match(navigation, /aria-current=\{activeWorkId === work\.id/);
});

test("uses existing Spinner, and plaza-style sidebar remains flush, not a floating card", () => {
  const chat = file(base + "practice-chat.tsx");
  const side = file("forge_frontend_next/components/ui/workspace-sidebar.module.css");
  const studio = file(base + "practice.module.css");
  assert.match(chat, /import \{ LoadingState, Spinner \} from "\.\.\/\.\.\/components\/ui\/state"/);
  assert.match(chat, /<Spinner size="sm"/);
  assert.match(side, /border-right:1px solid/);
  assert.match(side, /border-radius:0/);
  assert.match(studio, /\.layout \.sidebar\{[^}]*border-radius:0/);
});
