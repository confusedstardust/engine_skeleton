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
  assert.match(chat, /message\.timeline\?\.length \|\| message\.billing/);
  assert.match(chat, /billing=\{message\.billing\}/);
  assert.match(chat, /timeline=\{message\.timeline \?\? \[\]\}/);
  assert.match(chat, /message\.durationMs \?\? message\.billing\?\.durationMs/);
  assert.doesNotMatch(chat, /<TaskReceipt/);
  assert.doesNotMatch(chat, /latestReceipt/);
  assert.match(chat, /rows=\{2\}/);
  assert.doesNotMatch(chat, /AI 生成内容使用前请核对知识准确性与交互流程/);
  assert.doesNotMatch(chat, /<span className=\{styles\.badge\}>智能助手/);
  assert.match(css, /max-width:880px/);
  assert.match(css, /@media\(prefers-reduced-motion:reduce\)/);
});

test("gold timeline header merges settled credits, elapsed time and creation stages", () => {
  const usage = read(app + "task-usage.ts");
  const timeline = read(app + "creation-timeline.tsx");
  const css = read(app + "creation-timeline.module.css");
  const projection = read(app + "practice-conversation.ts");
  const api = read("forge_frontend_next/lib/conversation-api.ts");
  assert.match(usage, /billingStatus === "captured"/);
  assert.match(usage, /chargedCredits != null/);
  assert.match(usage, /模型未返回用量 · 未扣积分/);
  assert.match(timeline, /getTaskUsageTitle\(billing\)/);
  assert.match(timeline, /Clock3 size=\{14\}/);
  assert.match(timeline, /用时 \{elapsed\}/);
  assert.match(timeline, /aria-expanded=\{visible\}/);
  assert.match(timeline, /timeline\.length > 0 && <ol/);
  assert.doesNotMatch(timeline, /创作过程<|输入 Token|输出 Token|缓存输入|统计仅包含|<Gauge/);
  assert.match(css, /linear-gradient\(115deg,#fffaf0,#fff1d9\)/);
  assert.match(css, /@media\(max-width:360px\)/);
  assert.match(projection, /billing: message\.metadata\?\.billing/);
  assert.match(api, /billing\?:/);
});

test("HTML preview offers fullscreen, without a download webpage button", () => {
  const preview = read(app + "animation-preview.tsx");
  const host = read("forge_frontend_next/components/gesture/gesture-work-host.tsx");
  assert.match(preview, /GestureWorkHost/);
  assert.match(host, /requestFullscreen/);
  assert.doesNotMatch(preview, /下载 HTML|link\.download|createObjectURL|revokeObjectURL/);
});

test("wide conversation and compact composer keep independent sizing", () => {
  const css = read(app + "practice.module.css");
  const chat = read(app + "practice-chat.tsx");
  const workspace = read(app + "use-practice-workspace.ts");
  const timelineCss = read(app + "creation-timeline.module.css");
  assert.match(css, /layout:not\(\.layoutWithInspector\) \.chat\{width:100%/);
  assert.match(css, /\.composer:hover:not\(:focus-within\)/);
  assert.match(css, /\.composer:focus-within::before/);
  assert.match(timelineCss, /\.timelineToggle\{/);
  assert.match(workspace, /server\.artifacts\[0\]\?\.artifactId/);
  assert.doesNotMatch(chat, /!busy && latestReceipt/);
});
