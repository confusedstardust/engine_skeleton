const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const path=require("node:path");
const folder=path.resolve(__dirname,"../nar_agent/examples");
for(const name of ["gesture-classification.html","gesture-seasons.html"]){
 test("Standalone Bridge demo parses as JS and has noncamera interaction: "+name,()=>{
   const html=fs.readFileSync(path.join(folder,name),"utf8");
   assert.match(html,/data-nar-gesture="v1"/);
   assert.doesNotMatch(html,/getUserMedia|@mediapipe|<script[^>]+src=/i);
   const scripts=[...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)].map(x=>x[1]);
   assert.equal(scripts.length,1);
   assert.doesNotThrow(()=>new vm.Script(scripts[0]));
   assert.match(html,/data-gesture-dwell/);
   assert.match(html,/window\.NarrativeGesture\?\.on/);
 });
}
