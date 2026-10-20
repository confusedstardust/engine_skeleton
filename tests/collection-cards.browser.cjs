const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.CARD_TEST_URL || 'http://127.0.0.1:3001';
(async () => {
  const browser = await chromium.launch({ headless: true, channel: process.env.BROWSER_CHANNEL || 'chrome' });
  try {
    const page = await browser.newPage();
    page.setDefaultTimeout(10000);
    const mutations = [];
    let published = true;
    let failTitle = true;
    const job = { id: 'test-job', title: '测试作品', status: 'DONE', has_published_build: true, build_state: 'CURRENT', options: { generation_mode: 'advanced' } };
    const assets = [
      { id: 'a1', file_id: 'f1', name: '测试素材', kind: 'BACKGROUND', mime_type: 'image/png', url: '', owner_user_id: 'u1', source_type: 'UPLOADED', visibility: 'PRIVATE' },
      { id: 'a2', file_id: 'f2', name: '公共素材', kind: 'BACKGROUND', mime_type: 'image/png', url: '', owner_user_id: 'other', source_type: 'GENERATED', visibility: 'PUBLIC' },
    ];
    await page.route('**/api/forge/**', route => {
      const path = new URL(route.request().url()).pathname;
      const method = route.request().method();
      if (method !== 'GET') mutations.push({ path, method });
      let data = {};
      if (path.endsWith('/auth/me')) data = { id: 'u1', name: 'Tester' };
      else if (path.endsWith('/jobs')) data = { jobs: [job] };
      else if (path.endsWith('/title')) { if(failTitle) return route.fulfill({status:503,json:{detail:'作品重命名暂不可用'}}); job.title = route.request().postDataJSON().title; data = { job }; }
      else if (path.endsWith('/nodes')) data = { job, nodes: [{key:'game_design_completed',exists:true,content:'Scene:start.txt\n旁白:原始旁白;\nchangeScene:end.txt;\nEnding:end.txt\n旁白:结束;'}], scenes: [] };
      else if (path.endsWith('/ecosystem-publication')) {
        if (method === 'DELETE') published = false;
        if (method === 'POST') published = true;
        data = { published };
      } else if (path.endsWith('/published-flow')) data = { nodes: [{ id: 'start', label: '开始', kind: 'start' }], edges: [], revision: 1 };
      else if (path.endsWith('/assets/review')) data = { assets: [], voices: [], available_voices: [], scene_music: [], music_assets: [], particle_effects: { effects: [], scenes: [] } };
      else if (path.endsWith('/assets')) data = { assets, total: 2, has_more: false, next_offset: 2 };
      return route.fulfill({ json: data });
    });
    await page.route('**/play/**/cover*', route => route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900"><rect width="1600" height="900" fill="#907b65"/></svg>' }));
    await page.goto(`${base}/history/`);
    const card = page.locator('.history-row');
    await card.waitFor();
    assert.equal(await card.locator('.history-actions').count(), 0);
    assert.ok((await card.getByRole('link').getAttribute('href')).endsWith('?edit=1'));
    await card.click({ button: 'right' });
    await page.getByRole('menuitem', { name: '更新发布', exact: true }).waitFor();
    assert.equal(await page.getByRole('menuitem').first().textContent(), '开始游戏');
    assert.equal(await page.getByRole('menuitem').first().evaluate(el=>getComputedStyle(el).color),'rgb(165, 30, 56)');
    assert.ok((await card.getByRole('img').getAttribute('src')).includes('/play/test-job/cover?revision='));
    for (const name of ['开始游戏', '编辑', '打开习题', '流程图', '取消生态发布']) {
      assert.equal(await page.getByRole('menuitem', { name, exact: true }).count(), 1);
    }
    await page.getByRole('menuitem', { name: '流程图', exact: true }).click();
    await page.getByRole('dialog', { name: '最新流程图' }).waitFor();
    assert.ok(page.url().includes('/history'));
    await page.getByRole('button', { name: '关闭', exact: true }).click();
    await card.locator('.nos-card-more').click();
    await page.getByRole('menuitem', { name: '更新发布', exact: true }).click();
    await page.getByText('已发布到教师资源广场。', { exact: true }).waitFor();
    assert.equal(await page.locator('.app-toast').evaluate(el=>getComputedStyle(el).position),'fixed','operation feedback floats above content');
    assert.equal(await page.locator('.app-toast').getAttribute('data-tone'),'success');
    await page.getByRole('button',{name:'关闭提示',exact:true}).click();
    await page.locator('.app-toast').waitFor({state:'hidden'});
    assert.ok(mutations.some(m => m.method === 'POST' && m.path.endsWith('/ecosystem-publication')));
    await card.locator('.nos-card-more').click();
    await page.getByRole('menuitem', { name: '取消生态发布', exact: true }).click();
    await page.getByRole('alertdialog').getByRole('button', { name: '取消', exact: true }).click();
    assert.equal(mutations.filter(m => m.method === 'DELETE').length, 0);
    await card.locator('.nos-card-more').click();
    await page.getByRole('menuitem', { name: '取消生态发布', exact: true }).click();
    await page.getByRole('alertdialog').getByRole('button', { name: '确认', exact: true }).click();
    await page.getByText('已取消生态发布。', { exact: true }).waitFor();
    await page.locator('.app-toast').waitFor({state:'hidden',timeout:6000});
    await card.locator('.nos-card-more').click();
    await page.getByRole('menuitem', { name: '编辑', exact: true }).click();
    await page.getByText('草稿编辑中', { exact: true }).waitFor();
    assert.ok(page.url().includes('edit=1'));
    await page.getByRole('button',{name:'2 场景',exact:true}).click();
    await page.locator('textarea.laper-block-body').first().fill('未保存的新旁白');
    await page.getByRole('button',{name:'退出编辑',exact:true}).click();
    await page.getByRole('alertdialog').getByRole('button',{name:'取消',exact:true}).click();
    assert.equal(await page.locator('textarea.laper-block-body').first().inputValue(),'未保存的新旁白');
    assert.ok(page.url().includes('/jobs/test-job'));
    await page.getByRole('button',{name:'退出编辑',exact:true}).click();
    await page.getByRole('alertdialog').getByRole('button',{name:'确认',exact:true}).click();
    await page.waitForURL(url=>url.pathname.replace(/\/$/,'') === '/history');
    await card.locator('.nos-card-more').click();
    await page.getByRole('menuitem',{name:'重命名',exact:true}).click();
    await page.getByRole('dialog',{name:'重命名作品'}).waitFor();
    await page.getByRole('button',{name:'取消',exact:true}).click();
    await page.getByRole('button',{name:'重命名作品：测试作品'}).click();
    await page.getByRole('textbox',{name:'作品名称',exact:true}).fill('新作品名称');
    await page.getByRole('button',{name:'保存',exact:true}).click();
    await page.getByRole('alert').filter({hasText:'作品重命名暂不可用'}).waitFor();
    assert.equal(await page.getByRole('textbox',{name:'作品名称',exact:true}).inputValue(),'新作品名称');
    failTitle=false;
    await page.getByRole('textbox',{name:'作品名称',exact:true}).fill('A'.repeat(160));
    await page.getByRole('button',{name:'保存',exact:true}).click();
    await page.getByRole('dialog',{name:'重命名作品'}).waitFor({state:'hidden'});
    await card.getByRole('link',{name:'打开作品：'+'A'.repeat(160),exact:true}).waitFor();
    assert.ok(mutations.some(m=>m.path.endsWith('/title') && m.method==='PUT'));
    await page.setViewportSize({width:390,height:844});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'mobile card does not overflow');

    await page.route('**/play/**/cover*', route => route.fulfill({status:404}));
    await page.reload();
    await card.locator('.history-cover img').waitFor({state:'attached'});
    await page.waitForFunction(()=>document.querySelector('.history-cover img')?.style.visibility==='hidden');
    assert.equal(await card.getByText('封面暂不可用',{exact:true}).count(),1);
    await page.goto(`${base}/my-assets/`);
    const owned = page.getByRole('button', { name: '素材操作：测试素材' });
    const other = page.getByRole('button', { name: '素材操作：公共素材' });
    await owned.click();
    assert.equal(await page.getByRole('menuitem', { name: '重命名', exact: true }).count(), 0);
    await other.click();
    await page.getByRole('menu', { name: '素材操作：公共素材' }).waitFor();
    assert.equal(await page.getByRole('menuitem').count(), 1);
    await page.keyboard.press('Tab');
    await page.getByRole('menu').waitFor({ state: 'hidden' });
    await owned.click();
    await page.getByRole('menuitem', { name: '删除素材', exact: true }).click();
    await page.getByRole('alertdialog').getByRole('button', { name: '取消', exact: true }).click();
    await page.goto(`${base}/assets/`);
    await page.locator('.asset-library-card').first().getByRole('button').first().waitFor();
    assert.equal(await page.getByRole('button', { name: /删除素材|修改素材名称/ }).count(), 0);
    console.log('PASS: history publication/update/unpublish confirmation, shared flow modal, direct draft edit; asset rename removed and delete permissions preserved');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
