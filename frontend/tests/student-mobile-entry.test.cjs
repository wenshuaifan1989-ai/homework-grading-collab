const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const root = path.resolve(__dirname, '..')
const ts = require(path.join(root, 'node_modules/typescript'))
const vue = require(path.join(root, 'node_modules/vue'))
function compile(source, context = {}) {
  const module = { exports: {} }
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText,
    { module, exports: module.exports, URL,
      setTimeout() { throw Error('mobile entry must not schedule polling') }, setInterval() { throw Error('mobile entry must not schedule polling') }, ...context })
  return module.exports
}
const helpers = compile(fs.readFileSync(path.join(root, 'src/student/mobileEntry.ts'), 'utf8'))
const { createMobileEntrySession, validMobileEntryLink } = helpers
const studentId = 456
const link = (id = studentId) => ({ student_id: id, scope: 'student-workspace', phone_url: 'https://student.example.invalid/mobile/start', qr_image: 'data:image/png;base64,iVBORw0KGgo=' })
function deferred() { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b }); return { promise, resolve, reject } }

test('mobile entry accepts the existing fixed workspace QR and rejects other identities or unsafe responses', () => {
  assert.equal(validMobileEntryLink(link(), studentId), true)
  for (const patch of [{student_id:789},{scope:'upload'},{phone_url:'/mobile/start'},{phone_url:'javascript:alert(1)'},
    {phone_url:'https://user:password@example.invalid/'},{qr_image:'data:image/svg+xml;base64,abcd'},
    {qr_image:'https://example.invalid/qr.png'},{qr_image:'data:image/png;base64,not-a-png'}])
    assert.equal(validMobileEntryLink({...link(),...patch},studentId),false)
  for (const id of [0,-1,1.5,Number.MAX_SAFE_INTEGER+1]) assert.equal(validMobileEntryLink(link(),id),false)
})

test('one request prepares an entry only; repeated starts preserve the same QR without polling or reading homework', async () => {
  const pending = deferred(), states = []; let calls = 0
  const session = createMobileEntrySession({createLink: async () => { calls++; return pending.promise },
    getAssignments() { throw Error('entry must not query homework') }}, studentId, state => states.push(state))
  const first = session.start(); await session.start(); assert.equal(calls,1)
  pending.resolve(link()); await first
  const ready = states.at(-1)
  assert.equal(ready.phase,'ready'); assert.equal(ready.link.phone_url,link().phone_url)
  await session.start(); await session.start(); await new Promise(setImmediate)
  assert.equal(calls,1); assert.equal(states.at(-1).link.qr_image,ready.link.qr_image)
  assert.equal('items' in states.at(-1),false); assert.equal('receipt' in states.at(-1),false)
  session.stop(); await session.start(); assert.equal(calls,1)
})

test('missing contracts and invalid students perform no requests; invalid responses never expose a link', async () => {
  let calls = 0
  for (const [provider,id] of [[undefined,studentId],[{createLink:async()=>{calls++;return link()}},0]]) {
    let state; const session=createMobileEntrySession(provider,id,next=>{state=next}); await session.start()
    assert.equal(state.phase,'unavailable'); assert.equal(state.link,null)
  }
  assert.equal(calls,0)
  let state
  const session=createMobileEntrySession({createLink:async()=>link(789)},studentId,next=>{state=next})
  await session.start(); assert.equal(state.phase,'error'); assert.equal(state.link,null)
})

test('a failed read can be retried and closing ignores its late result', async () => {
  let calls=0, state
  const session=createMobileEntrySession({createLink:async()=>{if(++calls===1)throw Error('offline');return link()}},studentId,next=>{state=next})
  await session.start(); assert.equal(state.phase,'error')
  await session.start(); assert.equal(state.phase,'ready'); assert.equal(calls,2)
  session.stop()
  const pending=deferred(), states=[]
  const closing=createMobileEntrySession({createLink:()=>pending.promise},studentId,next=>states.push(next))
  const request=closing.start(); closing.stop(); const count=states.length
  pending.resolve(link()); await request
  assert.equal(states.length,count); assert.equal(states.at(-1).link,null)
})

function componentHarness(provider, clipboard = {}) {
  const source=fs.readFileSync(path.join(root,'src/components/student/StudentMobileEntry.vue'),'utf8').match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1]
  const props={studentId}, events=[], watchers=[]
  let mount, unmount, opens=0, closes=0
  const component=compile(source+'\nexport {dialog,state,copied,close,copyLink,retry};',{
    defineProps:()=>props,defineEmits:()=>event=>events.push(event),navigator:{clipboard},
    require:name=>name==='vue'?{...vue,onMounted:callback=>{mount=callback},onBeforeUnmount:callback=>{unmount=callback},watch:(_source,callback)=>watchers.push(callback)}
      :name==='@/student/mobileEntry'?helpers:name==='@/student/experience'?{studentExperience:{mobileEntry:provider}}:{},
  })
  component.dialog.value={showModal(){opens++},close(){closes++}}
  return {...component,props,events,mount:()=>mount(),unmount:()=>unmount(),changed:()=>watchers.forEach(callback=>callback()),opens:()=>opens,closes:()=>closes}
}

test('changing the child cancels the former entry and closing prevents late clipboard UI changes', async () => {
  const old=deferred(), copy=deferred(); const requests=[]
  const h=componentHarness({createLink:id=>{requests.push(id);return id===studentId?old.promise:Promise.resolve(link(id))}}, {writeText:()=>copy.promise})
  await h.mount(); h.props.studentId=789; h.changed(); await new Promise(setImmediate)
  assert.equal(h.state.value.link.student_id,789)
  old.resolve(link()); await new Promise(setImmediate); assert.equal(h.state.value.link.student_id,789)
  const copying=h.copyLink(); h.close(); copy.resolve(); await copying
  assert.equal(h.copied.value,false); assert.deepEqual(h.events,['close'])
  h.close(); assert.deepEqual(h.events,['close'])
  assert.deepEqual(requests,[studentId,789]); h.unmount()
})

test('unmount before the mount tick never opens a detached entry or requests a QR', async () => {
  let calls=0
  const h=componentHarness({createLink:async()=>{calls++;return link()}})
  const mounting=h.mount(); h.unmount(); await mounting
  assert.equal(h.opens(),0); assert.equal(calls,0)
})

test('rendered entry contains one QR and its address without upload actions or assignment progress', async () => {
  const {parse,compileScript}=require(path.join(root,'node_modules/@vue/compiler-sfc'))
  const {renderToString}=require(path.join(root,'node_modules/@vue/server-renderer'))
  const descriptor=parse(fs.readFileSync(path.join(root,'src/components/student/StudentMobileEntry.vue'),'utf8')).descriptor
  const compiled=compileScript(descriptor,{id:'mobile-entry-render',inlineTemplate:true})
  const component=compile(compiled.content,{navigator:{},require:name=>name==='vue'?{...vue,ref:value=>vue.ref(value&&value.phase==='loading'?{phase:'ready',link:link(),busy:false,error:''}:value)}
    :name==='@/student/mobileEntry'?helpers:name==='@/student/experience'?{studentExperience:{}}:{}})
  const html=await renderToString(vue.createSSRApp(component.default,{studentId}))
  assert.equal((html.match(/class="qr"/g)||[]).length,1)
  assert.match(html,/手机端入口/); assert.match(html,/https:\/\/student\.example\.invalid\/mobile\/start/)
  assert.match(html,/拍照和提交在手机网页里完成/)
  assert.doesNotMatch(html,/扫码上传|手机交多份作业|作业进度|刷新作业|待提交|待复核|确认提交|拍照添加/)
})
