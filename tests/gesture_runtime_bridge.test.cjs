const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const path=require("node:path");
const ts=require("../forge_frontend_next/node_modules/typescript");
const root=path.resolve(__dirname,"..");
function load(relative,imports={}){
 const source=fs.readFileSync(path.join(root,"forge_frontend_next/lib/gesture-bridge",relative),"utf8");
 const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 const module={exports:{}};
 const factory=vm.runInNewContext("(function(require,module,exports){"+code+"\n})");
 factory(name=>{if(!(name in imports))throw Error("Unexpected dependency: "+name);return imports[name];},module,module.exports);
 return module.exports;
}
const manifest=load("manifest.ts");
const {GestureAdapter}=load("adapter.ts",{"./manifest":manifest});
const protocol=load("protocol.ts");
function hand(pose,x=.4,y=.4,pinch=.1,heldMs=0){
 return {pose,pinch,heldMs,features:{center:{x,y}},landmarks:Array.from({length:21},(_,i)=>({x,y}))};
}
function frame(t,h){return {t,hands:h?[h]:[]};}
test("pinch hysteresis, no-hand release and pointer cleanup",()=>{
 const emitted=[],a=new GestureAdapter(e=>emitted.push(e));
 a.consume(frame(0,hand("point",.4,.4,.8)));
 a.consume(frame(40,hand("point",.45,.4,.5)));
 a.consume(frame(80,hand("point",.45,.4,.2)));
 a.consume(frame(100,null));
 assert.equal(emitted.filter(x=>x.kind==="pinch"&&x.phase==="start").length,1);
 assert.equal(emitted.filter(x=>x.kind==="pinch"&&x.phase==="end").length,1);
 assert.equal(emitted.filter(x=>x.kind==="pinch"&&x.phase==="move").length,2);
 assert.equal(emitted.at(-1).kind,"pointer");
 assert.equal(emitted.at(-1).visible,false);
});
test("fist rotate only, point swipe gated, open palm reset once",()=>{
 const out=[],a=new GestureAdapter(e=>out.push(e));
 a.consume(frame(10,hand("fist",.4)));
 a.consume(frame(80,hand("fist",.48)));
 assert.equal(out.filter(x=>x.kind==="rotate").length,1);
 assert.ok(out.find(x=>x.kind==="rotate").deltaX>0);
 a.consume(frame(100,hand("point",.3,.4)));
 a.consume(frame(350,hand("point",.5,.4)));
 assert.equal(out.filter(x=>x.kind==="swipe").length,1);
 assert.equal(out.find(x=>x.kind==="swipe").direction,"right");
 a.consume(frame(400,hand("open",.5,.4,.1,950)));
 a.consume(frame(460,hand("open",.5,.4,.1,1100)));
 assert.equal(out.filter(x=>x.kind==="reset").length,1);
 a.consume(frame(500,hand("point",.5)));
 a.consume(frame(600,hand("open",.5,.4,.1,950)));
 assert.equal(out.filter(x=>x.kind==="reset").length,2);
});
test("Bridge protocol rejects stale sessions, replay, NaN and unauthorized messages",()=>{
 const sid="0123456789abcdef";
 const msg={channel:"nar-gesture",v:1,sessionId:sid,seq:0,type:"READY",info:{bridgeVersion:1}};
 assert.equal(protocol.validControlMessage(msg,sid,-1),true);
 assert.equal(protocol.validControlMessage(msg,sid,0),false);
 assert.equal(protocol.validControlMessage(msg,"different",-1),false);
 assert.equal(protocol.validControlMessage({...msg,type:"OPEN_CAMERA"},sid,-1),false);
 assert.equal(protocol.validControlMessage({...msg,type:"EVENT",event:{kind:"status",state:"running"}},sid,-1),false);
 assert.equal(protocol.isGestureEvent({kind:"rotate",deltaX:Infinity,x:.5,y:.5}),false);
 assert.equal(protocol.isGestureEvent({kind:"rotate",deltaX:.3,x:.5,y:.5}),false);
 assert.equal(protocol.isGestureEvent({kind:"pinch",phase:"move",x:NaN,y:0}),false);
 assert.equal(protocol.isGestureEvent({kind:"pointer",visible:true,x:1.2,y:.5}),false);
 assert.equal(protocol.isGestureEvent({kind:"swipe",direction:"up"}),false);
 assert.equal(protocol.isGestureEvent({kind:"reset",reason:"open-hold"}),true);
});

test("Sandbox Bootstrap accepts only host handshake and monotonic scoped events",async()=>{
 const {MessageChannel}=require("node:worker_threads");
 const bootstrap=load("bridge-bootstrap.ts").BRIDGE_BOOTSTRAP;
 const listeners={};
 const origin="https://www.narrativeos.cn";
 const win={
   parent:{},
   addEventListener(name,callback){listeners[name]=callback;}
 };
 const doc={currentScript:{getAttribute(name){return name==="data-parent-origin"?origin:null;}}};
 vm.runInNewContext(bootstrap,{window:win,document:doc,console,performance:{now:()=>500}});
 assert.equal(win.NarrativeGesture.version,1);
 const seen=[];
 win.NarrativeGesture.on("swipe",e=>seen.push(e.direction));
 const channel=new MessageChannel();
 try{
   const session="test-session-"+"a".repeat(24);
   const data={channel:"nar-gesture",v:1,type:"NAR_GESTURE_CONNECT",sessionId:session};
   listeners.message({source:{},origin,data,ports:[channel.port2]}); // wrong source
   const ready=new Promise(resolve=>channel.port1.once("message",resolve));
   listeners.message({source:win.parent,origin,data,ports:[channel.port2]});
   const acknowledged=await ready;
   assert.equal(acknowledged.type,"READY");
   assert.equal(acknowledged.sessionId,session);
   const event=(seq,sessionId=session)=>({channel:"nar-gesture",v:1,sessionId,seq,type:"EVENT",event:{kind:"swipe",direction:"left"}});
   const received=new Promise(resolve=>win.NarrativeGesture.on("swipe",resolve));
   channel.port1.postMessage(event(1));
   await received;
   assert.equal(seen.length,1);
   channel.port1.postMessage(event(1)); // replay
   channel.port1.postMessage(event(2,"wrong-session")); // stale session
   channel.port1.postMessage({...event(3),event:{kind:"pinch",phase:"move",x:Infinity,y:0}}); // malformed
   await new Promise(resolve=>setTimeout(resolve,20));
   assert.equal(seen.length,1);
   channel.port1.postMessage(event(4));
   await new Promise(resolve=>setTimeout(resolve,20));
   assert.equal(seen.length,2);
   listeners.pagehide();
 } finally {channel.port1.close();channel.port2.close();}
});
