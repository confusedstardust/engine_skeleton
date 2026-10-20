const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const baseUrl = process.env.CARD_TEST_URL || 'http://127.0.0.1:3001';

const image = (width, height) => 'data:image/svg+xml,' + encodeURIComponent(
  `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><rect width="100%" height="100%" fill="#778c86"/><rect x="2" y="2" width="${width - 4}" height="${height - 4}" fill="none" stroke="#a12d44" stroke-width="4"/></svg>`,
);
const fixtures = [
  ['wide', 'BACKGROUND', 1600, 900],
  ['standard', 'BACKGROUND', 1200, 900],
  ['portrait-bg', 'BACKGROUND', 800, 1200],
  ['panorama', 'BACKGROUND', 2400, 600],
  ['portrait', 'FIGURE', 500, 1000],
  ['square', 'FIGURE', 1000, 1000],
].map(([id, kind, width, height]) => ({
  id, file_id: id, kind, name: id, owner_user_id: 'user',
  mime_type: 'image/svg+xml', url: image(width, height),
}));

(async () => {
  const browser = await chromium.launch({ headless: true, channel: process.env.BROWSER_CHANNEL || 'chrome' });
  try {
    const page = await browser.newPage();
    await page.route('**/api/forge/**', route => {
      const pathname = new URL(route.request().url()).pathname;
      const json = pathname.endsWith('/auth/me') ? { id: 'user', name: 'Tester' }
        : pathname.endsWith('/assets') ? { assets: fixtures, total: fixtures.length, has_more: false, next_offset: fixtures.length }
        : {};
      return route.fulfill({ json });
    });
    await page.goto(`${baseUrl}/assets/`);
    await page.locator('.asset-library-card').nth(fixtures.length - 1).waitFor();
    for (const width of [1280, 768, 390]) {
      await page.setViewportSize({ width, height: 900 });
      for (const fixture of fixtures) {
        const img = page.getByRole('img', { name: fixture.name, exact: true });
        await img.scrollIntoViewIfNeeded();
        await img.evaluate(el => el.decode());
        const preview = img.locator('..');
        const box = await preview.boundingBox();
        const background = fixture.kind === 'BACKGROUND';
        assert.ok(Math.abs(box.width / box.height - (16 / 9)) < 0.01, `${fixture.id}: preview ratio at ${width}px`);
        assert.equal(await img.evaluate(el => getComputedStyle(el).objectFit), background ? 'cover' : 'contain');
        if (!background) {
          await img.hover();
          assert.equal(await img.evaluate(el => getComputedStyle(el).transform), 'none', 'figure remains uncropped on hover');
        }
      }
      assert.equal(await page.locator('.asset-library-grid').evaluate(el => getComputedStyle(el).alignItems), 'start');
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'no horizontal overflow');
    }
    console.log('PASS: six image shapes at desktop/tablet/mobile; background fill, figure containment and hover, mixed-row alignment, no horizontal overflow');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
