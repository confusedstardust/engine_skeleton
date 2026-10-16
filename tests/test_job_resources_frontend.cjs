const { test } = require('node:test');
const assert = require('node:assert/strict');
const { hookHarness } = require('./helpers/hook_harness.cjs');
const { loadFrontendTs } = require('./helpers/load_frontend_ts.cjs');
test('asset review failure preserves nodes and retries until recovery; focus refreshes idle jobs', async t => {
 const h = hookHarness(); let poll; let fail = true; let focus; const messages=[]; const errors=[];
 const previous=global.window;
 global.window={addEventListener:(name,fn)=>{if(name==='focus') focus=fn},removeEventListener:()=>{}};
 t.after(()=>{h.unmount(); if(previous===undefined) delete global.window; else global.window=previous});
 const nodes={job:{status:'DONE'},nodes:[]};
 const review={assets:[],music_asset_names:{'track.mp3':'Library title'}};
 const {useJobResources}=loadFrontendTs('./forge_frontend_next/hooks/use-job-resources.ts', {
  react:h.react, './use-polling':{usePolling:(task,options)=>{poll={task,options}}},
  '../lib/api-client':{forgeApi:async path=>{if(path.endsWith('/nodes')) return nodes; if(fail) throw Error('review unavailable'); return review}}
 });
 const render=()=>h.render(()=>useJobResources('job',m=>messages.push(m),e=>errors.push(e)));
 render(); assert.equal(await poll.task(new AbortController().signal),true);
 let value=render(); assert.equal(value.data,nodes); assert.equal(value.assetReview,null); assert.equal(poll.options.enabled,true);
 assert.deepEqual(errors,['review unavailable']);
 await value.refresh(); assert.deepEqual(messages,[]);
 fail=false; assert.equal(await poll.task(new AbortController().signal),false);
 value=render(); assert.equal(value.assetReview,review); assert.equal(poll.options.enabled,false);
 nodes.job.status='RUNNING'; focus(); await new Promise(resolve=>setImmediate(resolve));
 render(); assert.equal(poll.options.enabled,true);
});
