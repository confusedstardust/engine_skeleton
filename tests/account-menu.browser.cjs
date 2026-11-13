const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.CARD_TEST_URL || 'http://127.0.0.1:3001';

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  try {
    const page = await browser.newPage();
    let admin = false;
    let identityReads = 0;
    await page.route('**/api/forge/**', route => {
      const path = new URL(route.request().url()).pathname;
      let data = {};
      if (path.endsWith('/auth/me')) { identityReads++; data = { id: 'user', nickname: '测试用户', email: 'user@example.com', auth_type: 'sso' }; }
      else if (path.endsWith('/credits/balance')) data = { available: 148, reserved: 0 };
      else if (path.endsWith('/payments/subscription')) data = { subscription: null };
      else if (path.endsWith('/admin/me')) return route.fulfill({ status: admin ? 200 : 403, json: {} });
      else if (path.includes('/community')) data = { announcements: [], questions: [], has_more: false };
      else if (path.endsWith('/assets')) data = { assets: [], total: 0, has_more: false, next_offset: 0 };
      else if (path.endsWith('/jobs')) data = { jobs: [] };
      return route.fulfill({ json: data });
    });
    for (const allowed of [false, true]) {
      admin = allowed;
      let expected;
      for (const path of ['/', '/history/', '/assets/']) {
        await page.goto(base + path);
        await page.getByRole('button', { name: '测试用户的账户', exact: true }).click();
        const menu = page.locator('.account-popover');
        await menu.getByRole('link', { name: '账号设置', exact: true }).waitFor();
        await page.waitForFunction(allowed => document.querySelectorAll('.account-actions a').length === (allowed ? 6 : 5), allowed);
        const links = await menu.locator('.account-actions a').allTextContents();
        if (expected) assert.deepEqual(links, expected, 'page must not change account menu contents');
        expected = links;
        const settings = new URL(await menu.getByRole('link', { name: '账号设置', exact: true }).getAttribute('href'), base);
        assert.equal(settings.pathname, '/account');
        assert.equal(await menu.locator('.account-actions [aria-current]').count(), 0);
        assert.equal(await menu.getByRole('link', { name: '平台管理', exact: true }).count(), allowed ? 1 : 0);
        const close = menu.getByRole('button', { name: '关闭账户浮窗', exact: true });
        assert.equal(await close.locator('svg').count(), 1);
        await close.click();
        await menu.waitFor({ state: 'hidden' });
      }
    }
    await page.goto(base + '/');
    await page.getByRole('button', { name: '测试用户的账户', exact: true }).click();
    const reads = identityReads;
    await page.locator('.account-popover').getByRole('link', { name: '我的作品', exact: true }).click();
    await page.waitForURL(url => /\/history\/?$/.test(url.pathname));
    await page.getByRole('button', { name: '测试用户的账户', exact: true }).click();
    await page.locator('.account-popover').waitFor();
    assert.equal(identityReads, reads, 'client-side page navigation reuses the session identity');
    console.log('PASS: identical account menus across home/history/assets, settings link and admin permission gating');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
