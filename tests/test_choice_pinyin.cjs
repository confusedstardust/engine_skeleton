const {test}=require('node:test');
const assert=require('node:assert/strict');
const {renderToStaticMarkup}=require('react-dom/server');
const {loadFrontendTs}=require('./helpers/load_frontend_ts.cjs');
const compiler=loadFrontendTs('src/Core/parser/compileSentence.tsx',{
  '@/Core/util/match':loadFrontendTs('src/Core/util/match.ts'),
  '@/hooks/useEscape':{default:loadFrontendTs('src/hooks/useEscape.ts').default},
});
const choiceText=loadFrontendTs('src/Core/gameScripts/choose/ChoiceText.tsx',{'@/Core/parser/compileSentence':compiler});
test('choice text renders authored per-character and grouped ruby',()=>{
  const html=renderToStaticMarkup(choiceText.ChoiceText({text:'去[银](yín)[行](háng)，沿路[行走](xíng zǒu)'}));
  assert.equal((html.match(/<rt>/g)||[]).length,3);
  assert.ok(html.includes('<rt>háng</rt>'));
  assert.ok(!html.includes('[行]'));
});
test('literal brackets, spaces and escaped choice separators retain their text',()=>{
  assert.equal(renderToStaticMarkup(choiceText.ChoiceText({text:'普通[括号] A B'})),'普通[括号] A B');
  const html=renderToStaticMarkup(choiceText.ChoiceText({text:'[银](yín) | A B'}));
  assert.ok(html.includes('|'));
  assert.ok(html.includes(' A B')||html.includes('A'));
});
test('ruby display leaves choice visibility, enabled state and scene target unchanged',()=>{
  let mounted, selected, unmounted;
  const styles=new Proxy({}, {get:(_,key)=>String(key)});
  const webgal={gameplay:{isFastPreview:false,performController:{unmountPerform:value=>{unmounted=value;}}}};
  const {choose}=loadFrontendTs('src/Core/gameScripts/choose/index.tsx',{
    '@/Core/controller/scene/changeScene':{changeScene:(...args)=>{selected=args;}},
    '@/Core/gameScripts/label/jmp':{jmp:()=>{}},
    'react-dom':{default:{render:node=>{mounted=node;}}},
    './choose.module.scss':{default:styles},
    '@/store/store':{webgalStore:{}},
    '@/hooks/useSoundEffect':{useSEByWebgalStore:()=>({playSeClick:()=>{},playSeEnter:()=>{}})},
    '@/Core/WebGAL':{WebGAL:webgal},
    '@/Core/controller/gamePlay/scriptExecutor':{whenChecker:value=>value!=='false'},
    '@/hooks/useEscape':{default:loadFrontendTs('src/hooks/useEscape.ts').default},
    '@/hooks/useApplyStyle':{default:()=>((_,fallback)=>fallback)},
    'react-redux':{Provider:({children})=>children},
    '@/hooks/useFontFamily':{useFontFamily:()=> 'sans-serif'},
    '@/Core/util/getSentenceArg':{getNumberArgByKey:()=>null},
    './ChoiceText':choiceText,
    '@/Core/Modules/perform/performInterface':{},
  });
  const oldDocument=global.document;
  global.document={getElementById:()=>({})};
  try{
    const perform=choose({content:'[false]->[禁](jìn)用:disabled.txt|(false)->隐藏:hidden.txt|[银行](yín háng):bank.txt',args:[]});
    perform.startFunction();
    const ui=mounted.props.children.type(mounted.props.children.props);
    const options=ui.props.children;
    assert.equal(options.length,2);
    options[0].props.children.props.onClick();
    assert.equal(selected,undefined);
    options[1].props.children.props.onClick();
    assert.equal(unmounted,'choose');
    assert.deepEqual(selected,['bank.txt','[银行](yín háng)']);
    assert.equal(perform.blockingNext(),true);
  }finally{global.document=oldDocument;}
});
