const test = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const root = join(__dirname, "..");
const read = path => readFileSync(join(root, path), "utf8");

test("Practice workbench shares the established navigation primitives", () => {
  const navigation = read("forge_frontend_next/app/practice/practice-navigation.tsx");
  const sidebar = read("forge_frontend_next/components/ui/workspace-sidebar.tsx");
  const page = read("forge_frontend_next/app/practice/page.tsx");
  assert.match(navigation, /from "\.\.\/\.\.\/components\/ui\/workspace-sidebar"/);
  assert.match(navigation, /from "\.\.\/\.\.\/components\/account-menu"/);
  assert.doesNotMatch(navigation, /function NavGlyph|<svg/);
  assert.match(sidebar, /import BrandLogo from "\.\.\/brand-logo"/);
  assert.match(sidebar, /import \{ Button \} from "\.\/button"/);
  assert.match(sidebar, /from "lucide-react"/);
  assert.match(page, /navigation=\{\(\{ collapsed, onToggle \}\) =>/);
});

test("Collapsing sidebar preserves the resizable studio and recent work route", () => {
  const resizable = read("forge_frontend_next/app/practice/resizable-workspace.tsx");
  const css = read("forge_frontend_next/app/practice/practice.module.css");
  const navigation = read("forge_frontend_next/app/practice/practice-navigation.tsx");
  assert.match(resizable, /effectiveNavWidth = navCollapsed \? 64 : navWidth/);
  assert.match(resizable, /collapsed: navCollapsed/);
  assert.match(resizable, /disabled=\{navCollapsed\}/);
  assert.match(navigation, /encodeURIComponent\(work.id\)/);
  assert.match(css, /\.layout \.sidebar\[data-collapsed=false\]/);
});

test("Portal and workbench icons use a pinned library instead of local SVG copies", () => {
  const pkg = JSON.parse(read("forge_frontend_next/package.json"));
  const lock = JSON.parse(read("forge_frontend_next/package-lock.json"));
  assert.equal(pkg.dependencies["lucide-react"], "^1.69.0");
  assert.equal(lock.packages["node_modules/lucide-react"].version, "1.69.0");
  assert.equal(lock.packages[""].dependencies["lucide-react"], pkg.dependencies["lucide-react"]);
});
