const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.CARD_TEST_URL || 'http://127.0.0.1:3001';
const waitUntil = async check => { for(let i=0;i<100;i++){ if(check())return; await new Promise(r=>setTimeout(r,20)); } throw Error('Timed out waiting for request'); };
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try {
  const page=await browser.newPage();
  let releaseInitialJobs;
  const initialJobs = new Promise(resolve => { releaseInitialJobs = resolve; });
  let firstJobsRead = true;
  let published=false, posting=false, finishPost, finishRead, reads=0, failPost=false, failDelete=false, failRead=false;
  const job={id:'review-job',title:'审查作品',status:'DONE',build_state:'CURRENT',has_published_build:true,options:{generation_mode:'advanced'}};
  await page.route('**/api/forge/**',async route=>{
   const path=new URL(route.request().url()).pathname, method=route.request().method(); let data={};
   if(path.endsWith('/auth/me')) data={id:'owner',name:'Owner'};
   else if(path.endsWith('/jobs')){if(firstJobsRead){firstJobsRead=false;await initialJobs;}data={jobs:[job]};}
   else if(path.endsWith('/nodes'))data={job,nodes:[],scenes:[]};
   else if(path.endsWith('/assets/review'))data={assets:[],voices:[],available_voices:[],scene_music:[],music_assets:[],particle_effects:{effects:[],scenes:[]}};
   else if(path.endsWith('/ecosystem-publication')){
    if(method==='POST'){
     if(failPost)return route.fulfill({status:503,json:{detail:'发布暂时不可用'}});
     posting=true; await new Promise(r=>{finishPost=r}); published=true;posting=false;
    } else if(method==='DELETE'){
     if(failDelete)return route.fulfill({status:503,json:{detail:'取消发布暂时不可用'}});
     published=false;
    } else {
     reads++;
     if(failRead)return route.fulfill({status:503,json:{detail:'状态读取失败'}});
     if(posting){const snapshot=published;await new Promise(r=>{finishRead=r});return route.fulfill({json:{published:snapshot}});}
    }
    data={published};
   }
   return route.fulfill({json:data});
  });
  await page.goto(`${base}/history/`);
  await page.getByRole('status').filter({hasText:'正在加载我的作品'}).locator('.pending-spinner').waitFor();
  assert.equal(await page.getByText('暂无记录',{exact:true}).count(),0);
  releaseInitialJobs();
  const more=page.getByRole('button',{name:'作品操作：审查作品'});
  failRead=true;
  await more.click();
  await page.getByText(/HTTP 503.*状态读取失败/).waitFor();
  assert.equal(await page.getByRole('menuitem',{name:'读取发布状态…'}).getAttribute('aria-disabled'),'true');
  await page.keyboard.press('Escape'); failRead=false;
  await more.click(); await page.getByRole('menuitem',{name:'发布',exact:true}).waitFor();
  const initialReads=reads;
  await page.getByRole('menuitem',{name:'发布',exact:true}).click();await waitUntil(()=>finishPost);
  await more.click();await page.getByRole('menu').waitFor();
  await page.waitForTimeout(100);
  finishPost();await page.getByText('已发布到教师资源广场。',{exact:true}).waitFor();
  if(finishRead)finishRead();
  await page.waitForTimeout(100);
  assert.equal(await page.getByRole('menuitem',{name:'更新发布',exact:true}).count(),1,'late status read must not revert successful publication');
  assert.equal(reads,initialReads,'no status reads during mutation');
  await page.keyboard.press('Escape');
  failDelete=true;await more.click();await page.getByRole('menuitem',{name:'取消生态发布'}).click();
  await page.getByRole('alertdialog').getByRole('button',{name:'确认',exact:true}).click();
  await page.getByText(/HTTP 503.*取消发布暂时不可用/).waitFor();
  await more.click();await page.getByRole('menuitem',{name:'取消生态发布'}).waitFor();await page.keyboard.press('Escape');
  failDelete=false;await more.click();await page.getByRole('menuitem',{name:'取消生态发布'}).click();
  await page.getByRole('alertdialog').getByRole('button',{name:'确认',exact:true}).click();
  await page.getByText('已取消生态发布。',{exact:true}).waitFor();
  failPost=true;await more.click();await page.getByRole('menuitem',{name:'发布',exact:true}).click();
  await page.getByText(/HTTP 503.*发布暂时不可用/).waitFor();
  await more.click();await page.getByRole('menuitem',{name:'发布',exact:true}).waitFor();await page.keyboard.press('Escape');
  // A direct URL must not enable editing while a build is running.
  job.build_state='BUILDING';
  await page.goto(`${base}/history/`);
  await more.click();
  const progress=page.getByRole('menuitem',{name:'查看进度',exact:true});
  assert.equal(await progress.getAttribute('aria-disabled'),null,'rebuilding progress remains accessible');
  assert.equal(await progress.getAttribute('href'),'/jobs/review-job','progress must not request draft editing');
  assert.equal(await page.getByRole('menuitem',{name:'删除任务',exact:true}).isDisabled(),true);
  await progress.click();
  await page.getByRole('heading',{name:'正在应用修改',exact:true}).waitFor();
  assert.equal(await page.getByText('草稿编辑中',{exact:true}).count(),0);
  await page.goto(`${base}/jobs/review-job?edit=1`);await page.getByRole('heading',{name:'正在应用修改',exact:true}).waitFor();
  assert.equal(await page.getByText('草稿编辑中',{exact:true}).count(),0,'BUILDING must block direct edit even if status is DONE');
  job.status='RUNNING';job.build_state='CURRENT';await page.reload();
  await page.getByRole('heading',{name:'正在应用修改',exact:true}).waitFor();
  assert.equal(await page.getByText('草稿编辑中',{exact:true}).count(),0,'RUNNING blocks direct edit');
  job.status='DONE';await page.reload();await page.getByText('草稿编辑中',{exact:true}).waitFor();
  console.log('PASS: publication race, read/mutation errors and retry, direct edit respects BUILDING/RUNNING');
 } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
