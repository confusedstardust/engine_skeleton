const test = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const read = relative => readFileSync(path.join(root, relative), "utf8");

function protocol() {
  const ts = require("../forge_frontend_next/node_modules/typescript");
  const source = read("forge_frontend_next/app/practice/agent-choice-protocol.ts");
  const js = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const exports = {};
  vm.runInNewContext(js, { exports, JSON, Set, Array, String, Error }, {
    filename: "agent-choice-protocol.ts",
  });
  return exports;
}

const example = [
  "以下是分数诊断教学方案。",
  "[[NAR_UI_CHOICES_V1]]",
  JSON.stringify({
    question: "你希望先完成哪一项？",
    options: [
      { id: "a", label: "分镜与页面布局" },
      { id: "b", label: "交互与状态规格", description: "包含状态 JSON" },
      { id: "c", label: "学生任务单和检测题" },
    ],
    multiple: false, allowCustom: true,
  }),
  "[[/NAR_UI_CHOICES_V1]]",
].join("\n");

test("parse end-of-turn choices while preserving the readable answer body", () => {
  const { parseAgentChoiceMessage, formatAgentChoiceAnswer } = protocol();
  const parsed = parseAgentChoiceMessage(example);
  assert.equal(parsed.body, "以下是分数诊断教学方案。");
  assert.equal(parsed.choice.question, "你希望先完成哪一项？");
  assert.equal(parsed.choice.options.length, 3);
  assert.equal(parsed.choice.options[1].description, "包含状态 JSON");
  assert.equal(parsed.choice.allowCustom, true);
  assert.equal(formatAgentChoiceAnswer(parsed.choice, ["b"]), "我选择：交互与状态规格");
  assert.equal(formatAgentChoiceAnswer(parsed.choice, [], "我想要一份教师版讲义"),
    "补充要求：我想要一份教师版讲义");
});

test("multi-select supports combining multiple labels and custom input", () => {
  const { parseAgentChoiceMessage, formatAgentChoiceAnswer } = protocol();
  const text = example.replace('"multiple":false', '"multiple":true');
  const parsed = parseAgentChoiceMessage(text);
  assert.equal(parsed.choice.multiple, true);
  assert.equal(formatAgentChoiceAnswer(parsed.choice, ["a", "c"], "同时列出评价标准"),
    "我选择：分镜与页面布局、学生任务单和检测题\n补充要求：同时列出评价标准");
});

test("plain chat, invalid JSON, duplicate IDs and extra content do not create actions", () => {
  const { parseAgentChoiceMessage } = protocol();
  assert.equal(parseAgentChoiceMessage("请问你想先做哪个？").choice, null);
  assert.equal(parseAgentChoiceMessage(example.replace('"question":', '"invalid":')).choice, null);
  assert.equal(parseAgentChoiceMessage(example.replace('"id":"b"', '"id":"a"')).choice, null);
  assert.equal(parseAgentChoiceMessage(example + "\n外部内容").choice, null);
  assert.equal(parseAgentChoiceMessage(example.replace("[[/NAR_UI_CHOICES_V1]]", "")).choice, null);
  assert.equal(parseAgentChoiceMessage(example.replace('"id":"a"', '"id":"javascript:evil"')).choice, null);
});

test("choice cards route only user-confirmed answers through the same send path", () => {
  const chat = read("forge_frontend_next/app/practice/practice-chat.tsx");
  const work = read("forge_frontend_next/app/practice/use-practice-workspace.ts");
  const component = read("forge_frontend_next/app/practice/agent-choice-prompt.tsx");
  const teaching = read("nar_agent/agents/teaching.py");
  assert.match(chat, /parseAgentChoiceMessage\(message\.content\)/);
  assert.match(chat, /message\.choices \?\? parsed\?\.choice/);
  assert.match(chat, /i !== messages\.length - 1/);
  assert.match(chat, /onAnswer=\{\(answer, structured\) => \{ void send\(answer, structured\); \}\}/);
  assert.match(work, /async function send\(promptOverride\?: string\)/);
  assert.match(component, /其他（自己填写）/);
  assert.match(component, /choice\.multiple/);
  assert.match(component, /disabled/);
  assert.match(teaching, /\[\[NAR_UI_CHOICES_V1\]\]/);
  assert.match(teaching, /CHOICE_INSTRUCTIONS/);
});
