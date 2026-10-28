const {test}=require('node:test');
const assert=require('node:assert/strict');
const {renderToStaticMarkup}=require('react-dom/server');
const {loadFrontendTs}=require('./helpers/load_frontend_ts.cjs');
const mocks={
  '@/Core/util/match':loadFrontendTs('src/Core/util/match.ts'),
  '@/hooks/useEscape':{default:loadFrontendTs('src/hooks/useEscape.ts').default},
};
const compiler=loadFrontendTs('src/Core/parser/compileSentence.tsx',mocks);
const classes=new Proxy({}, {get:(_,name)=>String(name)});
let rendered, nextHandler, unmounted;
const webgal={events:{userInteractNext:{on:fn=>{nextHandler=fn;},off:()=>{nextHandler=null;}}},gameplay:{performController:{unmountPerform:()=>{unmounted++;}}}};
const {intro,compileIntroLines}=loadFrontendTs('src/Core/gameScripts/intro.tsx',{
  ...mocks,
  '@/Core/parser/compileSentence':compiler,
  '@/Stage/FullScreenPerform/fullScreenPerform.module.scss':{default:classes},
  '@/Core/WebGAL':{WebGAL:webgal},
  'react-dom':{default:{render:node=>{rendered=node;}}},
});
function capture(content,args=[]){
  const priorDocument=global.document;
  const container={style:{},childNodes:[{childNodes:[{childNodes:[{style:{animationDelay:'0ms'},getAnimations:()=>[]}]}]}]};
  global.document={getElementById:()=>container};
  unmounted=0;
  const perform=intro({content,args});
  try{
    perform.startFunction();
    const html=renderToStaticMarkup(rendered);
    if(args.some(arg=>arg.key==='userForward'))nextHandler();
    return {html,perform,unmounted};
  }finally{perform.stopFunction();global.document=priorDocument;}
}
test('intro renders the actual authored ruby instead of bracket syntax',()=>{
  const {html}=capture('一九三七年夏，法国[邮](yóu)[船](chuán)缓缓驶入上海港。');
  assert.match(html,/<ruby[^>]*>邮<rt>yóu<\/rt><\/ruby>/);
  assert.match(html,/<ruby[^>]*>船<rt>chuán<\/rt><\/ruby>/);
  assert.ok(!html.includes('[邮]'));
  assert.match(html,/rubyLine/);
});
test('plain intro, empty segments and escaped separators retain their meaning and timing',()=>{
  const text='普通[方括号] 与 空格\\|字面竖线||末段';
  const lines=compileIntroLines(text);
  assert.equal(lines.length,3);
  assert.equal(lines[0][0].plainText,'普通[方括号] 与 空格|字面竖线');
  const {html,perform}=capture(text);
  assert.ok(html.includes('普通[方括号] 与 空格|字面竖线'));
  assert.match(html,/animation-delay:1500ms/);
  assert.match(html,/animation-delay:3000ms/);
  assert.equal(perform.duration,5500);
  assert.equal(perform.goNextWhenOver,true);
});
test('style and tips coexist with ruby; typing animation remains on the whole segment',()=>{
  const {html}=capture('[邮](ruby=yóu style=color~red tips=邮寄)',[{key:'animation',value:'typingEffect'}]);
  assert.match(html,/<rt>yóu<\/rt>/);
  assert.match(html,/title="邮寄"/);
  assert.match(html,/typingEffect/);
});
test('userForward still finishes the perform by clicking after the segment is visible',()=>{
  const result=capture('[船](chuán)',[{key:'userForward',value:true}]);
  assert.equal(result.unmounted,1);
});
