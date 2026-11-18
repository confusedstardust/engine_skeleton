/* Deterministic gesture tests. Run against the source with the repo's pinned TypeScript. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ts = require("../forge_frontend_next/node_modules/typescript");
const base = path.resolve(__dirname,"../forge_frontend_next/lib/gesture");
const modules = new Map();
function load(name) {
  if (modules.has(name)) return modules.get(name).exports;
  const file = path.join(base,name+".ts");
  const source = fs.readFileSync(file,"utf8");
  const code = ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
  const module = {exports:{}};
  modules.set(name,module);
  new Function("require","module","exports",code)((id)=>{
    if (!/^\.\/[a-z-]+$/.test(id)) throw new Error("Unexpected import "+id);
    return load(id.slice(2));
  },module,module.exports);
  return module.exports;
}
const {GestureStateMachine} = load("gesture-state-machine");
const {validBindings} = load("gesture-types");
const {GestureBindingDispatcher} = load("gesture-dispatcher");
const {interpretHand} = load("gesture-interpreter");

const fist = (cx=.5,cy=.5)=>({x:.5,y:.5,cx,cy,pinchRatio:0.6,fist:true,pointer:false,palm:false});
const pointer = (x=.5,y=.5)=>({x,y,cx:.5,cy:.5,pinchRatio:1,fist:false,pointer:true,palm:false});
const palm = ()=>({x:.5,y:.5,cx:.5,cy:.5,pinchRatio:2,fist:false,pointer:false,palm:true});
const pinch = (x=.4,y=.4)=>({x,y,cx:x,cy:y,pinchRatio:.2,fist:false,pointer:false,palm:false});
const phases = (events)=>events.map(e=>e.gestureId+":"+e.phase);

{
  const m = new GestureStateMachine();
  assert.deepEqual(phases(m.update(fist(),0)),[]);
  assert.deepEqual(phases(m.update(fist(),110)),["fist_rotate:start"]);
  assert.deepEqual(phases(m.update(fist(.55,.47),190)),["fist_rotate:move"]);
  assert.equal(m.update(fist(.55,.47),250)[0].data.dx,0);
  assert.deepEqual(phases(m.update(null,300)),[]);
  assert.deepEqual(phases(m.update(null,440)),["fist_rotate:end"]);
  assert.deepEqual(phases(m.update(fist(.1,.1),500)),[]);
  assert.equal(m.update(fist(.1,.1),700)[0].phase,"start");
}
{
  const m = new GestureStateMachine();
  m.update(pinch(),0);
  assert.deepEqual(phases(m.update(pinch(),110)),["pinch:start"]);
  const move=m.update(pinch(.45,.46),150)[0];
  assert.equal(move.gestureId,"pinch");
  assert.equal(move.phase,"move");
  assert.deepEqual(phases(m.update(fist(),160)),["pinch:end"]);
}
{
  const m = new GestureStateMachine();
  m.update(pointer(),0);
  m.update(pointer(),120);
  m.setHoverTarget(true);
  assert.deepEqual(phases(m.update(pointer(),750)),["index_pointer:move"]);
  assert.deepEqual(phases(m.update(pointer(),900)),["index_pointer:move","index_pointer:click"]);
  assert.deepEqual(phases(m.update(pointer(),1100)),["index_pointer:move"]);
  // A quick 20% pointer movement within 500ms is a swipe, so dwell is locked
  // until the pointer gesture is released and activated again.
  assert.deepEqual(phases(m.update(pointer(.7,.5),1200)),["index_pointer:move","index_pointer:swipe"]);
  assert.deepEqual(phases(m.update(pointer(.7,.5),2000)),["index_pointer:move"]);
  m.update({...pointer(.7,.5),pointer:false},2100);
  m.update(pointer(.7,.5),2200);
  m.update(pointer(.7,.5),2310);
  m.setHoverTarget(true);
  assert.deepEqual(phases(m.update(pointer(.7,.5),3100)),["index_pointer:move","index_pointer:click"]);
}
{
  const m = new GestureStateMachine();
  m.update(pointer(.2,.5),0);
  m.update(pointer(.2,.5),110);
  m.setHoverTarget(true);
  assert.deepEqual(phases(m.update(pointer(.42,.5),320)),["index_pointer:move","index_pointer:swipe"]);
  assert.deepEqual(phases(m.update(pointer(.42,.5),1100)),["index_pointer:move"]);
}
{
  const m = new GestureStateMachine();
  assert.deepEqual(phases(m.update(palm(),0)),[]);
  assert.deepEqual(phases(m.update(palm(),900)),["open_palm_hold:trigger"]);
  assert.deepEqual(phases(m.update(palm(),2300)),[]);
}
{
  const manifest={schemaVersion:"0.2.0",gestures:[
    {id:"fist_rotate",events:["start","move","end"],outputs:["dx","dy"],suggestedActions:["rotate"]},
    {id:"open_palm_hold",events:["trigger"],outputs:[],suggestedActions:["reset"]}]};
  const bindings={schemaVersion:"0.2.0",bindings:[
    {gesture:"fist_rotate",phases:["move"],action:"rotate"},
    {gesture:"open_palm_hold",phases:["trigger"],action:"reset"}]};
  assert.ok(validBindings(bindings.bindings,manifest));
  assert.equal(validBindings([{gesture:"fist_rotate",phases:["move"],action:"eval"}],manifest),false);
  assert.equal(validBindings([{gesture:"fist_rotate",phases:["move"],action:"rotate"},{gesture:"fist_rotate",phases:["move"],action:"rotate"}],manifest),false);
  const sent=[];
  const dispatch=new GestureBindingDispatcher(bindings,manifest,(a,e)=>sent.push([a,e]));
  dispatch.dispatch([{gestureId:"fist_rotate",phase:"move",timestamp:1,data:{dx:.2,dy:0}}]);
  dispatch.dispatch([{gestureId:"fist_rotate",phase:"move",timestamp:2,data:{dx:NaN,dy:0}}]);
  assert.equal(sent.length,1);assert.equal(sent[0][0],"rotate");
}
{
  assert.equal(interpretHand([]),null);
  assert.equal(interpretHand(Array.from({length:21},()=>({x:NaN,y:.5}))),null);
}
console.log("gesture-runtime: deterministic state machine / bindings / cleanup fixtures passed");
