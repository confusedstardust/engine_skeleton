const test = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const read = p => readFileSync(path.join(root, p), "utf8");
const app = "forge_frontend_next/app/practice/";

test("NarAgent keeps real streaming text alongside live HTML/animation milestones", () => {
  const chat = read(app + "practice-chat.tsx");
  const workspace = read(app + "use-practice-workspace.ts");
  const hook = read(app + "use-nar-conversation.ts");
  assert.match(chat, /<CreationTimeline timeline=\{activeTask\.timeline\}/);
  assert.match(chat, /publicBrief=\{activeTask\.public_brief\}/);
  assert.match(chat, /streamText && <article/);
  assert.match(hook, /conversationApi\.turnStatus/);
  assert.match(hook, /setActiveTask\(response\.task/);
  assert.match(workspace, /server\.streamText, activeTask/);
});

test("compact composer reuses Radix primitives, avoids stale disclaimer and badge", () => {
  const chat = read(app + "practice-chat.tsx");
  const css = read(app + "practice.module.css");
  assert.match(chat, /from "@radix-ui\/react-scroll-area"/);
  assert.match(chat, /<ScrollArea\.Root/);
  assert.match(chat, /message\.billing && <TaskReceipt value=\{message\.billing\} compact/);
  assert.doesNotMatch(chat, /latestReceipt/);
  assert.match(chat, /rows=\{2\}/);
  assert.doesNotMatch(chat, /AI 生成内容使用前请核对知识准确性与交互流程/);
  assert.doesNotMatch(chat, /<span className=\{styles\.badge\}>智能助手/);
  assert.match(css, /max-width:880px/);
  assert.match(css, /@media\(prefers-reduced-motion:reduce\)/);
});

test("usage receipt displays only actual settlement status, not an invented cost", () => {
  const receipt = read(app + "task-receipt.tsx");
  const projection = read(app + "practice-conversation.ts");
  const api = read("forge_frontend_next/lib/conversation-api.ts");
  assert.match(receipt, /@radix-ui\/react-collapsible/);
  assert.match(receipt, /billingStatus === "captured"/);
  assert.match(receipt, /usageStatus/);
  assert.match(receipt, /未返回用量时不推算扣费/);
  assert.match(projection, /billing: message\.metadata\?\.billing/);
  assert.match(api, /billing\?:/);
});


test("wide conversation and compact composer keep independent sizing", () => {
  const css = read(app + "practice.module.css");
  const chat = read(app + "practice-chat.tsx");
  const workspace = read(app + "use-practice-workspace.ts");
  const receiptCss = read(app + "task-receipt.module.css");
  assert.match(css, /layout:not\(\.layoutWithInspector\) \.chat\{width:100%/);
  assert.match(css, /\.composer:hover:not\(:focus-within\)/);
  assert.match(css, /\.composer:focus-within::before/);
  assert.match(receiptCss, /\.compact \.trigger/);
  assert.match(workspace, /server\.artifacts\[0\]\?\.artifactId/);
  assert.doesNotMatch(chat, /!busy && latestReceipt/);
});
