const test = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const read = name => readFileSync(path.join(root, name), "utf8");

test("inspector uses icon-rich actions and removes redundant instructions/buttons", () => {
  const preview = read("forge_frontend_next/app/practice/work-inspector.tsx");
  const css = read("forge_frontend_next/app/practice/practice.module.css");
  assert.match(preview, /FolderOpen/);
  assert.match(preview, /PencilLine/);
  assert.match(preview, /Share2/);
  assert.match(preview, /撤回发布/);
  assert.match(preview, /分享作品/);
  assert.match(preview, /在我的作品中查看/);
  assert.doesNotMatch(preview, /继续修改|更新广场发布|已保存到我的作品|可直接操作预览中的控件|公开前请先检查知识准确性/);
  assert.match(css, /\.inspectorActions \.inspectorActionPrimary/);
  assert.match(css, /linear-gradient\(140deg/);
});

test("share entry is always visible; unpublished requires a publish prompt", () => {
  const inspector = read("forge_frontend_next/app/practice/work-inspector.tsx");
  const shell = read("forge_frontend_next/app/practice/practice-shell.tsx");
  const lib = read("forge_frontend_next/app/practice/use-practice-library.ts");
  assert.match(inspector, /<Share2/);
  assert.match(shell, /open=\{Boolean\(shareNoticeArtifactId\)\}/);
  assert.match(shell, /请先发布作品/);
  assert.match(lib, /item\.publicationStatus !== "published"/);
  assert.match(lib, /setShareNoticeArtifactId\(artifactId\)/);
});

test("saved works expose seven commands in exactly requested order", () => {
  const page = read("forge_frontend_next/app/history/page.tsx");
  const cards = read("forge_frontend_next/app/history/saved-works-cards.tsx");
  assert.match(page, /<SavedWorksCards works=\{filteredSavedWorks\}/);
  const actions = [...cards.matchAll(/\{ id: "(open|edit|share|rename|cover|publication|delete)"/g)]
    .map(match => match[1]);
  assert.deepEqual(actions, ["open", "edit", "share", "rename", "cover", "publication", "delete"]);
  assert.match(cards, /history-status done">已完成</);
  assert.match(cards, /workApi\.remove\(remove\.id\)/);
  assert.match(cards, /await workApi\.unpublish\(remove\.id\)/);
  assert.match(cards, /<Link href=\{player\} className="history-cover"/);
});

test("owner and public work viewers share the player while maintaining auth boundary", () => {
  const player = read("forge_frontend_next/app/practice/works/[workId]/page.tsx");
  const service = read("forge_frontend_next/app/practice/practice-work-service.ts");
  const workApi = read("forge_frontend_next/lib/work-api.ts");
  assert.match(player, /const ownerView = new URLSearchParams/);
  assert.match(player, /forgeApi<PlayerWork>\(/);
  assert.match(player, /await workApi\.get\(workId\)/);
  assert.ok(player.includes('/api/forge/works/${workId}/assets/'));
  assert.doesNotMatch(player, /createObjectURL|URL\\.revokeObjectURL/);
  assert.match(player, /sandbox="allow-scripts"/);
  assert.match(service, /loadSavedWork/);
  assert.match(workApi, /remove: \(id: string\)/);
});
