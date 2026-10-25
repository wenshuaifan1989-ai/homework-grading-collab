const assert=require('node:assert/strict');
const {test}=require('node:test');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const ts=require(path.join(root,'node_modules/typescript'));
const vue=require(path.join(root,'node_modules/vue'));
const compiled=ts.transpileModule(fs.readFileSync(path.join(root,'src/student/device.ts'),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText;
function load(globals={}) {
  const module={exports:{}}; let mount,unmount;
  vm.runInNewContext(compiled,{module,exports:module.exports,...globals,require:name=>name==='vue'?{...vue,onMounted:fn=>{mount=fn;},onBeforeUnmount:fn=>{unmount=fn;}}:{}});
  return {...module.exports,mount:()=>mount?.(),unmount:()=>unmount?.()};
}
const {isStudentHandheldDevice}=load();

test('Android phones and tablets, iPhones, iPads and optional client hints select direct mobile actions',()=>{
  for(const hints of [
    {userAgent:'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit Chrome Mobile Safari'},
    {userAgent:'Mozilla/5.0 (Linux; Android 14; Tablet) AppleWebKit Chrome Safari'},
    {userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)'},
    {userAgent:'Mozilla/5.0 (iPad; CPU OS 18_0 like Mac OS X)'},
    {userAgent:'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15)',platform:'MacIntel',maxTouchPoints:5},
    {userAgent:'Unknown desktop UA',mobile:true},
    {userAgent:'Unknown desktop UA',coarsePointer:true,maxTouchPoints:5},
    {userAgent:'Android tablet in desktop mode',mobile:false},
  ]) assert.equal(isStudentHandheldDevice(hints),true,JSON.stringify(hints));
});

test('desktop narrow windows and fine-pointer touch devices retain computer actions',()=>{
  for(const hints of [
    {},{userAgent:'Mozilla/5.0 Windows NT 10.0 Win64 x64'},
    {userAgent:'Mozilla/5.0 Macintosh Intel Mac OS X',platform:'MacIntel',maxTouchPoints:0},
    {userAgent:'Desktop UA',mobile:false,maxTouchPoints:10,coarsePointer:false},
    {coarsePointer:true,maxTouchPoints:0},
  ]) assert.equal(isStudentHandheldDevice(hints),false,JSON.stringify(hints));
});

test('SSR and browsers without matchMedia or userAgentData are safe and expose a readonly hint',()=>{
  const ssr=load(); const ssrRef=ssr.useStudentHandheld();
  assert.equal(ssrRef.value,false); assert.equal(vue.isReadonly(ssrRef),true); ssr.mount(); ssr.unmount();
  const browser=load({navigator:{userAgent:'Android',maxTouchPoints:5},window:{}});
  assert.equal(browser.useStudentHandheld().value,true); browser.mount(); browser.unmount();
});

test('pointer changes update the UI hint and the listener is removed on unmount',()=>{
  let listener,removed=0;
  const query={matches:false,addEventListener(event,fn){assert.equal(event,'change');listener=fn;},removeEventListener(event,fn){assert.equal(fn,listener);removed++;}};
  const h=load({navigator:{userAgent:'Desktop UA',maxTouchPoints:5,userAgentData:{mobile:false}},window:{matchMedia:()=>query}});
  const value=h.useStudentHandheld(); assert.equal(value.value,false); h.mount();
  query.matches=true; listener(); assert.equal(value.value,true);
  query.matches=false; listener(); assert.equal(value.value,false);
  h.unmount(); assert.equal(removed,1);
});

test('older mobile browsers use the legacy media listener and clean it up',()=>{
  let listener,removed=0;
  const query={matches:true,addListener(fn){listener=fn;},removeListener(fn){assert.equal(fn,listener);removed++;}};
  const h=load({navigator:{userAgent:'Unknown UA',maxTouchPoints:1},window:{matchMedia:()=>query}});
  assert.equal(h.useStudentHandheld().value,true); h.mount(); h.unmount(); assert.equal(removed,1);
});
