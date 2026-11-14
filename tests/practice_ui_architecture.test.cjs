const test = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync, existsSync } = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const read = file => readFileSync(path.join(root, file), "utf8");
const practice = "forge_frontend_next/app/practice/";

test("NarAgent route delegates generation, library and conversation rendering", () => {
  const page = read(practice + "page.tsx");
  assert.ok(page.split("\n").length < 125, "route should stay a small composition component");
  assert.match(page, /usePracticeWorkspace/);
  assert.match(page, /<PracticeChat workspace=\{workspace\}/);
  assert.doesNotMatch(page, /forgeApi|workApi|<textarea|<button|<svg/);
  assert.match(page, /<WorkbenchHeader/);
  assert.match(read("forge_frontend_next/app/layout.tsx"), /<SiteFooter\s*\/>/);
});

test("Shared controls and icons are reused rather than hand-rolled", () => {
  const chat = read(practice + "practice-chat.tsx");
  const timeline = read(practice + "creation-timeline.tsx");
  const inspector = read(practice + "work-inspector.tsx");
  const share = read(practice + "work-share-dialog.tsx");
  const resizer = read(practice + "resizable-workspace.tsx");
  assert.match(chat, /from "lucide-react"/);
  assert.match(chat, /from "\.\.\/\.\.\/components\/ui\/button"/);
  assert.match(timeline, /from "lucide-react"/);
  assert.match(timeline, /<Button variant="unstyled"/);
  assert.match(inspector, /<CloseButton /);
  assert.match(share, /<CloseButton /);
  assert.match(resizer, /<GripVertical /);
});

test("Single work service handles deep links, history and save/publish", () => {
  const service = read(practice + "practice-work-service.ts");
  const workspace = read(practice + "use-practice-workspace.ts");
  const library = read(practice + "use-practice-library.ts");
  assert.match(workspace, /loadSavedWork\(savedId\)/);
  assert.match(library, /loadSavedWork\(workId, versionId\)/);
  assert.match(library, /persistArtifact\(work\)/);
  assert.match(library, /persistArtifact\(item, \{/);
  assert.match(service, /function savedWorkPreview/);
  assert.match(service, /function persistArtifact/);
});

test("Main's resource listing survives integration at its own route", () => {
  const route = practice + "resources/page.tsx";
  assert.ok(existsSync(path.join(root, route)));
  assert.match(read(route), /practice-tools/);
  assert.match(read(practice + "practice-navigation.tsx"), /\/practice\/resources/);
  assert.match(read("forge_frontend_next/next.config.mjs"), /api\/forge\/practice-tools/);
});
