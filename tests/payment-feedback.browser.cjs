const assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const base=process.env.CARD_TEST_URL||'http://127.0.0.1:3001';
(async()=>{const browser=await chromium.launch({headless:true,channel:'chrome'});try{
 const page=await browser.newPage();page.setDefaultTimeout(10000);
 let failCreate=true, failHistory=false, reads=0;
 const order={id:'order1',name:'私人支付测试',status:'PENDING',fulfillment_status:'PENDING',credits:1,payable_fen:10,pay_url:'weixin://test'};
 await page.route('**/api/forge/**',route=>{
  const path=new URL(route.request().url()).pathname, method=route.request().method();
  let data={};
  if(path.endsWith('/auth/me'))data={id:'user',name:'User',auth_type:'sso'};
  else if(path.endsWith('/credits/balance')||path.endsWith('/test/balance'))data={available:10,total:10,reserved:0};
  else if(path.endsWith('/test/products'))data={};
  else if(path.endsWith('/test/orders')){
   if(method==='POST')return failCreate?route.fulfill({status:503,json:{detail:'下单测试失败'}}):route.fulfill({json:order});
   if(failHistory)return route.fulfill({status:503,json:{detail:'初始订单加载测试失败'}});data=[];
  }else if(path.endsWith('/test/orders/order1')){reads++;return route.fulfill({status:503,json:{detail:'订单查询测试失败'}});}
  return route.fulfill({json:data});
 });
 await page.goto(`${base}/payment-test/`);
 await page.getByRole('button',{name:'创建 ¥0.10 测试订单',exact:true}).click();
 await page.locator('.app-toast[data-tone=error]').filter({hasText:'下单测试失败'}).waitFor();
 assert.equal(await page.locator('.private-payment-test > [role="alert"]').count(),0,'operation error does not duplicate page feedback');
 await page.getByRole('button',{name:'关闭提示',exact:true}).click();
 failCreate=false;await page.getByRole('button',{name:'创建 ¥0.10 测试订单',exact:true}).click();
 await page.getByRole('dialog').getByRole('alert').filter({hasText:'订单查询测试失败'}).waitFor();
 assert.equal(await page.locator('.app-toast').count(),0,'checkout error only appears inside active dialog');
 const readsBeforeClose=reads;
 await page.getByRole('dialog').getByRole('button',{name:'关闭支付窗口',exact:true}).click();
 await page.waitForTimeout(12000);
 assert.ok(reads>readsBeforeClose,'pending order still polls after checkout closes');
 assert.equal(await page.locator('.app-toast').count(),0,'closed checkout background polling stays quiet');
 failHistory=true;await page.goto(`${base}/payment-test/`);
 await page.locator('.private-payment-test > [role="alert"]').filter({hasText:'初始订单加载测试失败'}).waitFor();
 assert.equal(await page.locator('.app-toast').count(),0,'initial load failure is not a transient toast');
 console.log('PASS: order creation error toast, active checkout inline error without duplication, initial load error stays in content');
}finally{await browser.close()}})().catch(error=>{console.error(error);process.exitCode=1});
