const assert = require('node:assert/strict')
const { test } = require('node:test')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const root = path.resolve(__dirname, '..')
const ts = require(path.join(root, 'node_modules/typescript'))
const vue = require(path.join(root, 'node_modules/vue'))
const moduleInstance = { exports: {} }
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(root, 'src/student/mistakePrint.ts'), 'utf8'), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText, {
  module: moduleInstance, exports: moduleInstance.exports, atob, AbortController, setTimeout, clearTimeout,
})
const { prepareMistakePrint, validMistakeImage, safeQuestionImage, buildMistakePrintDocument, createMistakePrintJob } = moduleInstance.exports
const png = 'data:image/png;base64,iVBORw0KGgo='
const jpeg = 'data:image/jpeg;base64,/9j/4A=='
const item = (id = 101) => ({ id, student_id: 91, subject: 'math', assignment_id: 70, assignment_title: '合成代数作业', question_no: '3(2)', question: { correct_answer: 'UNRELEASED-SECRET', analysis: 'TEACHER-ANALYSIS' }, grading_result: { student_answer: 'PRIVATE-STUDENT-ANSWER', score: 0 }, crop_url: '/handwriting-with-answers', original_url: '/private-original', student_name: 'PRIVATE-NAME' })
const material = (id = 101) => ({ student_id: 91, mistake_id: id, question: { text: '求合成方程的解：x + 2 = 5。', complete: true, options: ['A. 2', 'B. 3'] }, standard_answer: { released: true, text: 'x = 3。' }, student_answer: 'PRIVATE-STUDENT-ANSWER' })
const selection = () => [{ item: item(), material: material() }, { item: item(102), material: { ...material(102), question: { text: '合成第二题：计算 6 ÷ 2。', options: null, complete: true }, standard_answer: { released: true, text: '3。' } } }]
const prepared = () => prepareMistakePrint(91, 'math', selection())
function deferred() { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b }); return { promise, resolve, reject } }
const tick = () => new Promise(setImmediate)

test('printing consumes only the confirmed adapter and never falls back to raw teacher answers', () => {
  const denied = prepareMistakePrint(91, 'math', [{ item: item(), material: null }])
  assert.equal(denied.entries.length, 0)
  assert.match(denied.issues[0].message, /尚未取得/)
  const ok = prepared()
  assert.equal(ok.issues.length, 0)
  assert.equal(ok.entries.length, 2)
  assert.equal(ok.entries[0].questionNo, '3(2)')
  const output = JSON.stringify(ok)
  for (const secret of ['UNRELEASED-SECRET', 'TEACHER-ANALYSIS', 'PRIVATE-STUDENT-ANSWER', 'PRIVATE-NAME', 'crop_url', 'score']) assert.equal(output.includes(secret), false)
})

test('student, subject, duplicate IDs and material identity are checked before a batch can print', () => {
  for (const selected of [
    [{ item: { ...item(), student_id: 92 }, material: material() }],
    [{ item: { ...item(), subject: 'english' }, material: material() }],
    [{ item: item(), material: { ...material(), mistake_id: 999 } }],
    [{ item: item(), material: { ...material(), student_id: 92 } }],
    [{ item: { ...item(), id: -1 }, material: material() }],
    [{ item: item(), material: material() }, { item: item(), material: material() }],
  ]) {
    const result = prepareMistakePrint(91, 'math', selected)
    assert.ok(result.issues.length)
    assert.throws(() => buildMistakePrintDocument(new FakeDocument(), result, 'split'), /先处理/)
  }
  for (const [student, subject] of [[0, 'math'], [91, ''], [91, '__unconfirmed__']]) assert.ok(prepareMistakePrint(student, subject, selection()).issues.length)
  assert.match(prepareMistakePrint(91, 'math', []).issues[0].message, /先选择/)
})

test('missing question, incomplete options or unreleased answers block the entire chosen batch', () => {
  for (const changed of [
    { ...material(), question: null },
    { ...material(), question: { ...material().question, complete: false } },
    { ...material(), question: { ...material().question, text: '  ' } },
    { ...material(), question: { ...material().question, options: ['A', null] } },
    { ...material(), standard_answer: { released: false, text: 'SHOULD-NOT-EXPOSE' } },
    { ...material(), standard_answer: { released: true, text: ' ' } },
    { ...material(), standard_answer: null },
  ]) {
    const selected = selection(); selected[1].material = { ...changed, mistake_id: 102 }
    const result = prepareMistakePrint(91, 'math', selected)
    assert.equal(result.entries.length, 1)
    assert.equal(result.issues[0].id, 102)
    const doc = new FakeDocument()
    assert.throws(() => buildMistakePrintDocument(doc, result, 'filled'), /先处理/)
    assert.equal(doc.body.children.length, 0)
    assert.equal(JSON.stringify(result).includes('SHOULD-NOT-EXPOSE'), false)
  }
})

test('only matching PNG/JPEG data signatures can become clean question images', () => {
  assert.equal(validMistakeImage(png), true)
  assert.equal(validMistakeImage(jpeg), true)
  assert.equal(safeQuestionImage(png), png)
  for (const bad of [undefined, null, '', '/crop.png', 'https://example.invalid/a.png', 'data:image/svg+xml;base64,PHN2Zy8+', 'data:image/png;base64,PGh0bWw+', 'data:image/jpeg;base64,iVBORw0KGgo=', 'data:image/png;base64,not-base64', 'data:image/png;base64,iVBORw0KGgo']) {
    assert.equal(validMistakeImage(bad), false)
    assert.equal(safeQuestionImage(bad), null)
  }
  const changed = selection(); changed[0].material.question.image_data_url = '/private-original'
  assert.match(prepareMistakePrint(91, 'math', changed).issues[0].message, /题图/)
})

test('adapter options and released text are copied and detached from later mutations', () => {
  const chosen = selection()
  chosen[0].item.question = null
  chosen[0].material.question.options = { A: '  合成一  ', B: '合成二' }
  chosen[0].material.question.image_data_url = png
  const result = prepareMistakePrint(91, 'math', chosen)
  assert.equal(result.issues.length, 0)
  assert.equal(result.entries[0].options.join('|'), 'A 合成一|B 合成二')
  chosen[0].material.question.options.A = 'MUTATED'
  chosen[0].material.standard_answer.text = 'CHANGED'
  assert.equal(result.entries[0].options[0], 'A 合成一')
  assert.equal(result.entries[0].answer, 'x = 3。')
})

class FakeElement extends EventTarget {
  constructor(tagName, ownerDocument) { super(); this.tagName = tagName.toUpperCase(); this.ownerDocument = ownerDocument; this.children = []; this.parentNode = null; this.style = {}; this.attributes = {}; this._text = ''; this.className = ''; this.complete = true; this.naturalWidth = 1 }
  set textContent(value) { this._text = String(value); this.children = [] }
  get textContent() { return this._text + this.children.map(child => child.textContent).join('') }
  appendChild(child) { child.parentNode = this; this.children.push(child); if (child.tagName === 'IFRAME') this.ownerDocument.onFrameAppend?.(child); return child }
  replaceChildren(...children) { this._text = ''; this.children = []; children.forEach(child => this.appendChild(child)) }
  setAttribute(name, value) { this.attributes[name] = value }
  remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter(child => child !== this); this.parentNode = null; this.removed = true }
}
class FakeDocument {
  constructor(options = {}) { this.options = options; this.documentElement = new FakeElement('html', this); this.head = new FakeElement('head', this); this.body = new FakeElement('body', this); this.fonts = { ready: options.fonts || Promise.resolve() }; this.frames = []; this.printCalls = 0; this.focusCalls = 0 }
  createElement(tag) {
    const element = new FakeElement(tag, this)
    if (tag === 'iframe') {
      element.contentDocument = new FakeDocument(this.options.frameOptions)
      element.contentWindow = new EventTarget()
      element.contentWindow.focus = () => { this.focusCalls++ }
      element.contentWindow.print = () => { this.printCalls++; this.options.onPrint?.(element) }
      this.frames.push(element)
    }
    if (tag === 'img' && this.options.onImage) this.options.onImage(element)
    return element
  }
  get images() { return descendants(this.body).filter(el => el.tagName === 'IMG') }
}
function descendants(root) { return root.children.flatMap(child => [child, ...descendants(child)]) }
function withClass(root, className) { return descendants(root).filter(el => el.className === className) }

test('filled print document uses per-question answers and literal text without student responses or HTML interpretation', () => {
  const doc = new FakeDocument(), result = prepared()
  result.entries[0].text = '<script>alert(1)</script> & 合成题干'
  result.entries[0].answer = '<img src=https://example.invalid/leak>'
  buildMistakePrintDocument(doc, result, 'filled')
  const questions = withClass(doc.body, 'question')
  assert.equal(questions.length, 2)
  assert.ok(questions[0].textContent.includes(result.entries[0].answer))
  assert.ok(questions[1].textContent.includes('3。'))
  assert.equal(withClass(doc.body, 'answers').length, 0)
  assert.equal(descendants(doc.body).some(el => ['SCRIPT', 'IMG'].includes(el.tagName)), false)
  assert.ok(doc.body.textContent.includes('3(2)'))
  for (const secret of ['PRIVATE-STUDENT-ANSWER', 'PRIVATE-NAME', 'TEACHER-ANALYSIS', 'UNRELEASED-SECRET']) assert.equal(doc.body.textContent.includes(secret), false)
  assert.ok(doc.head.textContent.includes('A4 portrait'))
})

test('split document has answer-free questions and a separate page with matching numbering and assignment sources', () => {
  const doc = new FakeDocument(), result = prepared()
  result.entries[0].imageDataUrl = png
  buildMistakePrintDocument(doc, result, 'split')
  const questions = withClass(doc.body, 'question'), answers = withClass(doc.body, 'answers')
  assert.equal(questions.length, 2); assert.equal(answers.length, 1)
  assert.equal(questions[0].textContent.includes('x = 3。'), false)
  assert.equal(withClass(questions[0], 'answer').length, 0)
  assert.equal(withClass(answers[0], 'answer-entry').length, 2)
  assert.ok(answers[0].textContent.includes('1. 合成代数作业 · 原题号 3(2)'))
  assert.ok(answers[0].textContent.includes('x = 3。'))
  assert.equal(doc.images[0].src, png)
  assert.ok(doc.head.textContent.includes('break-before:page'))
  const altered = prepared(); altered.entries[0].imageDataUrl = '/private-original'
  assert.throws(() => buildMistakePrintDocument(new FakeDocument(), altered, 'split'), /题图不可用/)
})

test('printing waits for the isolated document and its images before invoking its own print context', async () => {
  let loadedImage
  const host = new FakeDocument({ frameOptions: { onImage: element => { element.complete = false; loadedImage = element } } })
  host.onFrameAppend = frame => queueMicrotask(() => frame.dispatchEvent(new Event('load')))
  const result = prepared(); result.entries[0].imageDataUrl = png
  const states = [], job = createMistakePrintJob(host, { onBusyChange: state => states.push(state) })
  const printing = job.print(result, 'split')
  await tick()
  assert.equal(host.printCalls, 0)
  assert.equal(job.busy, true)
  assert.equal(await job.print(result, 'filled'), 'ignored')
  loadedImage.dispatchEvent(new Event('load'))
  assert.equal(await printing, 'opened')
  assert.equal(host.printCalls, 1)
  assert.equal(host.focusCalls, 1)
  assert.ok(host.frames[0].srcdoc.includes("default-src 'none'"))
  assert.equal(host.frames[0].srcdoc.includes('合成方程'), false)
  host.frames[0].contentWindow.dispatchEvent(new Event('afterprint'))
  assert.equal(job.busy, false)
  assert.equal(host.body.children.length, 0)
  assert.deepEqual(states, [true, false])
  job.dispose()
})

test('printing also waits for document fonts; cancellation removes the frame and ignores late readiness', async () => {
  const fonts = deferred()
  const host = new FakeDocument({ frameOptions: { fonts: fonts.promise } })
  host.onFrameAppend = frame => queueMicrotask(() => frame.dispatchEvent(new Event('load')))
  const job = createMistakePrintJob(host)
  const pending = job.print(prepared(), 'filled')
  await tick(); assert.equal(host.printCalls, 0)
  job.cancel()
  assert.equal(await pending, 'cancelled')
  assert.equal(host.body.children.length, 0)
  fonts.resolve(); await tick()
  assert.equal(host.printCalls, 0)
  job.dispose()
  assert.equal(await job.print(prepared(), 'filled'), 'ignored')
})

test('closing while the frame is loading prevents detached printing and a fresh retry creates one frame', async () => {
  const host = new FakeDocument()
  const job = createMistakePrintJob(host)
  const pending = job.print(prepared(), 'split')
  job.cancel(); host.frames[0].dispatchEvent(new Event('load'))
  assert.equal(await pending, 'cancelled')
  assert.equal(host.printCalls, 0)
  host.onFrameAppend = frame => queueMicrotask(() => frame.dispatchEvent(new Event('load')))
  assert.equal(await job.print(prepared(), 'split'), 'opened')
  assert.equal(host.printCalls, 1)
  assert.equal(host.body.children.length, 1)
  job.dispose()
  assert.equal(host.body.children.length, 0)
})

test('image and frame readiness failures never print incomplete sheets and can be retried', async () => {
  const host = new FakeDocument()
  const job = createMistakePrintJob(host, { readyTimeout: 5 })
  await assert.rejects(job.print(prepared(), 'split'), /未能加载/)
  assert.equal(host.body.children.length, 0)
  assert.equal(host.printCalls, 0)
  host.onFrameAppend = frame => queueMicrotask(() => frame.dispatchEvent(new Event('load')))
  host.options.frameOptions = { onImage: element => { element.complete = true; element.naturalWidth = 0 } }
  const result = prepared(); result.entries[0].imageDataUrl = png
  await assert.rejects(job.print(result, 'filled'), /题图尚未完整/)
  assert.equal(host.body.children.length, 0)
  assert.equal(host.printCalls, 0)
  host.options.frameOptions = {}
  assert.equal(await job.print(prepared(), 'split'), 'opened')
  job.dispose()
})

test('a cancelled native print dialog creates no success receipt and afterprint/fallback release all resources', async () => {
  const host = new FakeDocument({ onPrint: frame => frame.contentWindow.dispatchEvent(new Event('afterprint')) })
  host.onFrameAppend = frame => queueMicrotask(() => frame.dispatchEvent(new Event('load')))
  const job = createMistakePrintJob(host)
  assert.equal(await job.print(prepared(), 'split'), 'opened')
  assert.equal(job.busy, false)
  assert.equal(host.body.children.length, 0)
  host.options.onPrint = undefined
  const fallback = createMistakePrintJob(host, { cleanupTimeout: 5 })
  assert.equal(await fallback.print(prepared(), 'split'), 'opened')
  await new Promise(resolve => setTimeout(resolve, 12))
  assert.equal(fallback.busy, false)
  assert.equal(host.body.children.length, 0)
  fallback.dispose(); job.dispose()
})

function componentHarness(options = {}) {
  const source = fs.readFileSync(path.join(root, 'src/components/student/StudentMistakePrint.vue'), 'utf8').match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1]
  const props = vue.reactive({ studentId: 91, subject: 'math', selection: selection() })
  const events = [], pending = deferred()
  let mounted, unmount, busyCallback, calls = 0, cancels = 0, disposed = 0, opens = 0
  const fakeJob = { cancel: () => { cancels++; busyCallback?.(false) }, dispose: () => { disposed++; busyCallback?.(false) }, print: async () => { calls++; busyCallback(true); return pending.promise } }
  const compiled = { exports: {} }
  vm.runInNewContext(ts.transpileModule(source + '\nexport {dialog,layout,prepared,busy,error,printNotice,close,print};', { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText, {
    module: compiled, exports: compiled.exports, document: options.document || {},
    defineProps: () => props, defineEmits: () => event => events.push(event),
    require: name => name === 'vue' ? { ...vue, onMounted: cb => { mounted = cb }, onBeforeUnmount: cb => { unmount = cb } }
      : name === '@/student/device' ? { useStudentHandheld: () => vue.ref(!!options.handheld) }
      : name === '@/student/mistakePrint' ? { prepareMistakePrint, createMistakePrintJob: options.realJob ? createMistakePrintJob : (doc, options) => { busyCallback = options.onBusyChange; return fakeJob } } : {},
  })
  const api = compiled.exports
  api.dialog.value = { showModal: () => { opens++ }, close() {} }
  return { api, props, pending, events, mounted: () => mounted(), unmount: () => unmount(), calls: () => calls, cancels: () => cancels, disposed: () => disposed, opens: () => opens }
}

test('print modal defaults to split, refuses duplicate clicks and never claims physical output', async () => {
  const h = componentHarness(); await h.mounted()
  assert.equal(h.api.layout.value, 'split')
  const printing = h.api.print()
  await h.api.print(); assert.equal(h.calls(), 1)
  h.pending.resolve('opened'); await printing
  assert.match(h.api.printNotice.value, /已打开打印选择界面/)
  assert.equal(h.events.length, 0)
  h.api.close(); h.api.close()
  assert.deepEqual(h.events, ['close'])
  assert.ok(h.disposed())
  h.unmount()
})

test('print modal blocks unavailable answers, invalidates selection changes, and ignores late work after close', async () => {
  const h = componentHarness(); await h.mounted()
  h.props.selection[0].material.standard_answer.released = false
  await vue.nextTick()
  await h.api.print(); assert.equal(h.calls(), 0)
  h.props.selection[0].material.standard_answer.released = true
  await vue.nextTick()
  const printing = h.api.print()
  h.props.subject = 'english'; await vue.nextTick()
  assert.ok(h.cancels())
  h.api.close(); h.pending.resolve('opened'); await printing
  assert.equal(h.api.printNotice.value, '')
  h.unmount()
})

test('unmount before the mount tick never opens a detached print modal', async () => {
  const h = componentHarness(), mounting = h.mounted()
  h.unmount(); await mounting
  assert.equal(h.opens(), 0)
  await h.api.print(); assert.equal(h.calls(), 0)
})

test('handheld print uses the existing document job directly for both layouts and reports only the print selection stage',async()=>{
  const host=new FakeDocument({onPrint:frame=>frame.contentWindow.dispatchEvent(new Event('afterprint'))})
  host.onFrameAppend=frame=>queueMicrotask(()=>frame.dispatchEvent(new Event('load')))
  const h=componentHarness({handheld:true,document:host,realJob:true})
  await h.mounted()
  for(const layout of ['split','filled']) {
    h.api.layout.value=layout; await vue.nextTick()
    await h.api.print()
    assert.match(h.api.printNotice.value,/已打开打印选择界面/)
    assert.doesNotMatch(h.api.printNotice.value,/打印成功|打印完成|出纸/)
  }
  assert.equal(host.printCalls,2); assert.equal(host.frames.length,2)
  assert.equal(host.frames[0].attributes.sandbox,'allow-same-origin allow-modals')
  const firstDoc=host.frames[0].contentDocument,secondDoc=host.frames[1].contentDocument
  assert.equal(withClass(firstDoc.body,'answers').length,1)
  assert.equal(withClass(secondDoc.body,'answers').length,0)
  assert.equal(h.events.length,0); h.unmount()
})

test('handheld print modal renders local print instructions and a direct print action without QR links',async()=>{
  const {parse,compileScript}=require(path.join(root,'node_modules/@vue/compiler-sfc'))
  const {renderToString}=require(path.join(root,'node_modules/@vue/server-renderer'))
  const descriptor=parse(fs.readFileSync(path.join(root,'src/components/student/StudentMistakePrint.vue'),'utf8')).descriptor
  const compiled=compileScript(descriptor,{id:'handheld-mistake-print',inlineTemplate:true})
  const module={exports:{}}
  vm.runInNewContext(ts.transpileModule(compiled.content,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText,{
    module,exports:module.exports,
    require:name=>name==='vue'?vue:name==='@/student/device'?{useStudentHandheld:()=>vue.ref(true)}
      :name==='@/student/workbench'?{subjectLabel:()=>'数学'}
      :name==='@/student/mistakePrint'?{prepareMistakePrint,createMistakePrintJob}:{}
  })
  const html=await renderToString(vue.createSSRApp(module.exports.default,{studentId:91,subject:'math',selection:selection()}))
  assert.match(html,/mistake-print handheld/); assert.match(html,/在手机打印 \/ 存为 PDF/)
  assert.match(html,/直接使用本机的打印选择界面/); assert.match(html,/原题号 3\(2\)/)
  assert.doesNotMatch(html,/扫码|qr_image|phone_url|打印成功|PRIVATE-STUDENT-ANSWER|UNRELEASED-SECRET/)
})
