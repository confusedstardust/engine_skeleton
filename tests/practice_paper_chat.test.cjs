const test = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const read = file => readFileSync(path.resolve(__dirname, "..", file), "utf8");
const studio = "forge_frontend_next/app/practice/";

test("practice chat uses real user and branded assistant avatars without visible speaker labels", () => {
  const chat = read(studio + "practice-chat.tsx");
  const avatar = read(studio + "practice-message-avatar.tsx");
  const workspace = read(studio + "use-practice-workspace.ts");
  assert.match(chat, /<PracticeMessageAvatar role=\{message\.role\}/);
  assert.match(chat, /className=\{styles\.messagePaper\}/);
  assert.doesNotMatch(chat, /styles\.speaker|>教学助手<|>你<\/span>/);
  assert.match(avatar, /<BrandLogo size=\{36\}/);
  assert.match(avatar, /userAvatarUrl && <img/);
  assert.match(avatar, /onError=\{event => \{ event\.currentTarget\.hidden = true; \}\}/);
  assert.match(workspace, /avatar_url\?: string/);
  assert.match(workspace, /setUserAvatarUrl\(isSso/);
});

test("paper and sticky-note layouts distinguish speakers and adapt to mobile", () => {
  const css = read(studio + "practice.module.css");
  assert.match(css, /\.conversation\{[^}]*background-color:#f2e4c6/s);
  assert.match(css, /\.assistant\{[^}]*justify-content:flex-start/s);
  assert.match(css, /\.user\{[^}]*flex-direction:row-reverse/s);
  assert.match(css, /\.assistant \.messagePaper\{[^}]*#ffe5a1/s);
  assert.match(css, /\.user \.messagePaper\{[^}]*#cce2af/s);
  assert.match(css, /@media\(max-width:760px\)[\s\S]*\.messageAvatar\{/);
  assert.match(css, /@media\(prefers-reduced-motion:reduce\)\{\s*\.messagePaper/);
});

test("fireworks are decorative, motion-safe, and only triggered for new turns", () => {
  const chat = read(studio + "practice-chat.tsx");
  const avatar = read(studio + "practice-message-avatar.tsx");
  const css = read(studio + "practice.module.css");
  assert.match(chat, /if \(!sessionReady\) \{ seen\.current\.initialized = false; return; \}/);
  assert.match(chat, /lastKey !== previous\.lastKey/);
  assert.match(chat, /current\.slice\(-3\)/);
  assert.match(avatar, /Array\.from\(\{ length: 8 \}/);
  assert.match(css, /@keyframes avatarFirework/);
  assert.match(css, /\.avatarBurst\{display:none\}/);
});
