const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.CARD_TEST_URL || 'http://127.0.0.1:3001';
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 let page;
 try{
  page=await browser.newPage();page.setDefaultTimeout(10000);page.on("pageerror",error=>console.log("PAGE ERROR:",error.message,error.stack));
  let failDelete=true, failAdminPublish=true, failQuiz=true, failQuestion=true;
  let releaseUpload;
  const uploadGate = new Promise(resolve => { releaseUpload = resolve; });
  const job={id:'feedback-job',title:'反馈验证',status:'DONE',has_published_build:true,build_state:'CURRENT',options:{generation_mode:'advanced'}};
  const asset={id:'asset1',file_id:'file1',name:'私有素材',kind:'BACKGROUND',source_type:'UPLOADED',visibility:'PRIVATE',owner_user_id:'user',mime_type:'image/png',url:''};
  const plan={title:'反馈验证',characters:[],story_progression:[],endings:[]};
  const review={assets:[],voices:[],available_voices:[],scene_music:[],music_assets:[],particle_effects:{effects:[],scenes:[]}};
  await page.route('**/api/forge/**',async route=>{
   const path=new URL(route.request().url()).pathname, method=route.request().method(); let data={};
   const failure=detail=>route.fulfill({status:503,json:{detail}});
   if(path.endsWith('/auth/me'))data={id:'user',name:'测试用户',auth_type:'sso'};
   else if(path.endsWith('/credits/balance'))data={available:100,total:100,reserved:0};
   else if(path.endsWith('/auth/config'))data={mode:'sso'};
   else if(path.endsWith('/admin/me'))data={admin:true};
   else if(path.endsWith('/admin/dashboard'))return failure('看板暂时不可用');
   else if(path.endsWith('/admin/community'))data={announcements:[],questions:[{id:'q1',question:'如何开始创作？',answer:null,published:false,created_at:'2026-10-20'}],has_more:false};
   else if(path.includes('/admin/community/'))data={};
   else if(path.endsWith('/admin/assets/taxonomy'))data={};
   else if(path.endsWith('/admin/assets/upload')){await uploadGate;data={};}
   else if(path.includes('/admin/users/') && path.endsWith('/credits'))data={units:10,created:true};
   else if(path.includes('/admin/users/'))data={user:{id:'user',nickname:'测试用户',created_at:'2026-10-20',blocked:false},subscription:null,revision:1};
   else if(path.includes('/admin/games/') && path.endsWith('/ecosystem-publication')){
    if(method!=='GET' && failAdminPublish)return failure('管理端发布失败');
    data={published:method==='POST'};
   }
   else if(path.endsWith('/admin/games'))data={items:[{id:job.id,name:job.title,status:'SUCCEEDED',blocked:false}],page:1,total:1,total_pages:1,has_more:false};
   else if(path.endsWith('/admin/users'))data={items:[{id:'user',nickname:'测试用户',email:'test@example.com',blocked:false}],page:1,total:1,total_pages:1,has_more:false};
   else if(path.endsWith('/admin/assets'))data={items:[],page:1,total:0,total_pages:1,has_more:false};
   else if(path.endsWith('/favorite'))data={};
   else if(path.endsWith('/assets/asset1') && method==='DELETE'){
    if(failDelete)return failure('素材删除测试失败');data={deleted:true};
   }
   else if(path.endsWith('/assets'))data={assets:[asset],total:1,has_more:false,next_offset:1};
   else if(path.endsWith('/assets/review'))data=review;
   else if(path.endsWith('/nodes'))data={job,nodes:[{key:'narrative_plan',exists:true,content:JSON.stringify(plan)},{key:'game_design_completed',exists:true,content:'Scene:start.txt\n旁白:原文;\nchangeScene:end.txt;\nEnding:end.txt\n旁白:结束;'}],scenes:[]};
   else if(path.endsWith('/artifacts'))data={job};
   else if(path.endsWith('/ecosystem-publication'))data={published:method==='POST'};
   else if(path.endsWith('/quiz')){
    if(method==='POST'&&failQuiz)return failure('习题生成测试失败');
    data={status:method==='POST'?'QUEUED':'NOT_GENERATED',quiz:null,can_manage:true};
   }
   else if(path.endsWith('/community/messages') || path.endsWith('/community/questions')){
    if(method==='POST'&&failQuestion)return failure('发送测试失败');data={};
   }
   else if(path.endsWith('/community/mine'))data={questions:[],has_more:false};
   else if(path.endsWith('/community'))data={announcements:[],questions:[],has_more:false};
   return route.fulfill({json:data});
  });
  const toast=page.locator('.app-toast');
  const dismiss=async()=>{if(await toast.count())await toast.getByRole('button',{name:'关闭提示'}).click();};
  const expectToast=async(text,tone)=>{await toast.filter({hasText:text}).waitFor();assert.equal(await toast.getAttribute('data-tone'),tone);assert.equal(await toast.evaluate(el=>getComputedStyle(el).position),'fixed');assert.equal(await toast.count(),1);};
  await page.goto(`${base}/my-assets/`);
  await page.getByRole('button',{name:'收藏素材',exact:true}).click();await expectToast('已收藏素材','success');await dismiss();
  await page.getByRole('button',{name:'删除素材 私有素材',exact:true}).click();
  await page.getByRole('alertdialog').getByRole('button',{name:'确认',exact:true}).click();
  await page.getByRole('alertdialog').getByRole('alert').filter({hasText:'素材删除测试失败'}).waitFor();
  assert.equal(await toast.count(),0,'delete errors belong inside confirmation');
  failDelete=false;await page.getByRole('alertdialog').getByRole('button',{name:'确认',exact:true}).click();
  await expectToast('素材已删除','success');await dismiss();
  await page.goto(`${base}/jobs/feedback-job?edit=1`);
  await page.getByRole('button',{name:'2 剧情',exact:true}).click();
  await page.locator('textarea.laper-block-body').first().fill('已保存的新内容');
  await page.getByRole('button',{name:'仅保存草稿',exact:true}).click();
  await expectToast('场景草稿已保存','success');await dismiss();
  await page.getByRole('button',{name:'4 完成',exact:true}).click();
  await page.getByRole('button',{name:'发布',exact:true}).click();await expectToast('已发布到教师资源广场','success');await dismiss();
  assert.equal(await page.locator('.publication-message').count(),0);
  await page.goto(`${base}/practice/feedback-job/`);
  await page.getByRole('button',{name:'生成习题',exact:true}).click();await expectToast('习题生成测试失败','error');await dismiss();
  failQuiz=false;await page.getByRole('button',{name:'生成习题',exact:true}).click();await expectToast('习题已进入生成队列','success');await dismiss();
  await page.goto(`${base}/admin/`);
  await page.getByRole('tab',{name:'游戏',exact:true}).click();
  await page.getByRole('button',{name:'发布到教师资源广场',exact:true}).click();await expectToast('管理端发布失败','error');await dismiss();
  failAdminPublish=false;await page.getByRole('button',{name:'发布到教师资源广场',exact:true}).click();await expectToast('已发布到教师资源广场','success');await dismiss();
  await page.getByRole('tab',{name:'公告与问答',exact:true}).click();
  const form=page.getByRole('form',{name:'新公告'});
  await form.getByLabel('公告标题').fill('测试公告');await form.getByLabel(/公告正文/).fill('测试内容');await form.getByRole('button',{name:'发布公告',exact:true}).click();
  await expectToast('公告已发布','success');await dismiss();
  const reply=page.getByRole('form',{name:'回复：如何开始创作？'});
  await reply.getByLabel('管理员答复').fill('从首页开始');await reply.getByRole('button',{name:'保存答复'}).click();await expectToast('答复已保存','success');await dismiss();
  await page.getByRole('tab',{name:'素材',exact:true}).click();
  await page.getByRole('button',{name:'上传公共素材',exact:true}).click();
  const upload=page.getByRole('dialog',{name:'上传公共素材',exact:true});await upload.getByPlaceholder('输入用户看到的素材名称').fill('测试上传');
  await upload.locator('input[type=file]').setInputFiles({name:'test.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg==','base64')});
  await upload.getByRole('button',{name:'上传素材',exact:true}).click();
  await upload.locator('button[aria-busy="true"] .pending-spinner').first().waitFor();
  assert.equal(await upload.getByRole('button',{name:'关闭上传',exact:true}).isDisabled(),true);
  await page.keyboard.press('Escape');assert.equal(await upload.isVisible(),true);
  releaseUpload();await upload.waitFor({state:'hidden'});await expectToast('上传成功，已加入公共素材库','success');await dismiss();
  await page.getByRole('tab',{name:'用户',exact:true}).click();await page.getByRole('button',{name:'查看详情',exact:true}).click();
  const details=page.getByRole('dialog');await details.getByLabel('赠送数量').fill('10');await details.getByLabel('赠送原因').fill('验证提示');await details.getByRole('button',{name:'赠送积分',exact:true}).click();await expectToast('已赠送 10 积分','success');await dismiss();
  await details.getByLabel('修改原因').fill('验证提示');await details.getByRole('button',{name:'保存订阅',exact:true}).click();await expectToast('订阅已保存','success');
  await page.goto(`${base}/`);await dismiss();
  const question=page.getByRole('textbox',{name:'你的问题',exact:true});
  await question.fill('这是一条测试问题');await page.getByRole('button',{name:'发送',exact:true}).click();
  await page.getByRole('alert').filter({hasText:'发送测试失败'}).waitFor();
  assert.equal(await question.inputValue(),'这是一条测试问题');assert.equal(await toast.count(),0);
  failQuestion=false;await page.getByRole('button',{name:'发送',exact:true}).click();await expectToast('已发送','success');
  assert.equal(await question.inputValue(),'');
  console.log('PASS: dialog error visibility, workspace save, completion publication, quiz error/success, admin publication, announcement/reply, upload after close, user credit/subscription; one global host');
 }catch(error){console.log((await page.locator("body").innerText()).slice(0,2200));throw error;}finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1});
