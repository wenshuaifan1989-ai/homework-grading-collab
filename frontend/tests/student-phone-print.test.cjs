const assert = require('node:assert/strict')
const { test } = require('node:test')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const root = path.resolve(__dirname, '..')
const ts = require(path.join(root, 'node_modules/typescript'))
const vue = require(path.join(root, 'node_modules/vue'))
function load(relative) {
  const source = fs.readFileSync(path.join(root, 'src/student', relative), 'utf8')
  const module = { exports: {} }
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText,
    { module, exports: module.exports, URL, setTimeout, clearTimeout, require: name => assert.fail(`printing must not depend on the retired upload module: ${name}`) })
  return module.exports
}
const { createPhonePrintSession, validPrintLink } = load('phonePrint.ts')
const context = { student_id: 456, assignment_id: 123 }
const link = () => ({ ...context, purpose: 'print', phone_url: 'https://student.example.invalid/print?assignment=123', qr_image: 'data:image/png;base64,iVBORw0KGgo=' })
function deferred() { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b }); return { promise, resolve, reject } }
function harness(provider, boundContext = context) {
  const states = []
  const session = createPhonePrintSession(provider, boundContext, state => states.push(state))
  return { session, states, latest: () => states.at(-1) }
}
test('print QR requires matching learner and assignment, print purpose, HTTP(S), and a PNG data image', () => {
  assert.equal(validPrintLink(link(), context), true)
  for (const patch of [
    { student_id: 777 }, { assignment_id: 777 }, { purpose: 'upload' }, { purpose: undefined },
    { phone_url: 'javascript:alert(1)' }, { phone_url: 'https://user:password@example.invalid/print' },
    { phone_url: '/print' }, { qr_image: 'https://example.invalid/qr.png' },
    { qr_image: 'data:image/svg+xml;base64,PHN2Zz4=' }, { qr_image: 'data:image/png;base64,not-a-png' },
  ]) assert.equal(validPrintLink({ ...link(), ...patch }, context), false)
})
test('no supplied print contract presents an unavailable state and makes no request', async () => {
  const h = harness(undefined)
  await h.session.start()
  assert.equal(h.latest().phase, 'unavailable')
  assert.equal(h.latest().link, null)
  assert.equal(h.latest().busy, false)
})
test('invalid IDs never call the integration', async () => {
  let calls = 0
  for (const badContext of [{ ...context, student_id: 0 }, { ...context, assignment_id: -1 }, { ...context, student_id: 1.5 }]) {
    const h = harness({ createLink: async () => { calls++; return link() } }, badContext)
    await h.session.start()
    assert.equal(h.latest().phase, 'error')
  }
  assert.equal(calls, 0)
})
test('invalid or cross-purpose responses never expose a QR or report a successful print', async () => {
  for (const patch of [{ purpose: 'upload' }, { student_id: 999 }, { assignment_id: 999 }, { phone_url: 'file:///private' }]) {
    const h = harness({ createLink: async () => ({ ...link(), ...patch }) })
    await h.session.start()
    assert.equal(h.latest().phase, 'error')
    assert.equal(h.latest().link, null)
    assert.equal('printed' in h.latest(), false)
  }
})
test('a print link is requested directly without consulting an existing submission or polling progress', async () => {
  const calls = []
  const h = harness({
    createLink: async (...args) => { calls.push(args); return link() },
    getProgress: async () => { assert.fail('print must not query submission progress') },
    submitAssignment: async () => { assert.fail('print must not create a homework task') },
  })
  await h.session.start()
  assert.equal(h.latest().phase, 'ready')
  assert.deepEqual(calls, [[context.student_id, context.assignment_id]])
  assert.equal('receipt' in h.latest(), false)
})
test('manual retry recovers failure and rapid clicks do not overlap link requests', async () => {
  const pending = deferred(); let calls = 0
  const h = harness({ createLink: async () => { calls++; if (calls === 1) return pending.promise; return link() } })
  const first = h.session.start()
  await h.session.start(); await h.session.start()
  assert.equal(calls, 1)
  pending.reject(Error('synthetic network failure')); await first
  assert.equal(h.latest().phase, 'error')
  await h.session.start()
  assert.equal(calls, 2); assert.equal(h.latest().phase, 'ready')
})
test('stopping a print session ignores a late response and prevents restart', async () => {
  const pending = deferred(); let calls = 0
  const h = harness({ createLink: async () => { calls++; return pending.promise } })
  const start = h.session.start(), beforeStop = h.states.length
  h.session.stop(); pending.resolve(link()); await start; await h.session.start()
  assert.equal(calls, 1); assert.equal(h.states.length, beforeStop)
})
function componentHarness(provider, options = {}) {
  const source = fs.readFileSync(path.join(root, 'src/components/student/StudentPhonePrint.vue'), 'utf8').match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1]
  const props = vue.reactive({ studentId: context.student_id, assignment: { id: context.assignment_id, title: '合成作业', class_name: '合成班级', status: 'published', submitted: true, task_status: 'WAIT_REVIEW' } })
  const events = []
  let mounted, unmount, opens = 0, closes = 0
  const module = { exports: {} }
  vm.runInNewContext(ts.transpileModule(source + '\nexport {dialog, state, copied, copyError, copyLink, close, retry};', { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText, {
    module, exports: module.exports,
    defineProps: () => props, defineEmits: () => event => events.push(event), navigator: options.navigator || {},
    require: name => name === 'vue' ? { ...vue, onMounted: callback => { mounted = callback }, onBeforeUnmount: callback => { unmount = callback } }
      : name === '@/student/experience' ? { studentExperience: { phonePrint: provider } }
      : name === '@/student/phonePrint' ? { createPhonePrintSession } : {},
  })
  const api = module.exports
  api.dialog.value = { showModal() { opens++ }, close() { closes++ } }
  return { props, api, events, mounted: () => mounted(), unmount: () => unmount(), opens: () => opens, closes: () => closes }
}
test('submitted and pending-review homework still opens a print QR; same-ID replacement does not restart', async () => {
  let calls = 0
  const h = componentHarness({ createLink: async (studentId, assignmentId) => { calls++; return { ...link(), student_id: studentId, assignment_id: assignmentId } } })
  await h.mounted(); await new Promise(setImmediate)
  assert.equal(h.api.state.value.phase, 'ready'); assert.equal(calls, 1)
  h.props.assignment = { ...h.props.assignment, task_status: 'HOLD_REVIEW' }
  await vue.nextTick(); await new Promise(setImmediate)
  assert.equal(calls, 1)
  h.props.assignment = { ...h.props.assignment, id: 124 }
  await vue.nextTick(); await new Promise(setImmediate)
  assert.equal(calls, 2); assert.equal(h.api.state.value.link.assignment_id, 124)
  assert.equal(h.events.length, 0)
  h.api.close(); h.api.close()
  assert.deepEqual(h.events, ['close'])
  h.unmount()
})
test('changing context invalidates a late link and closing invalidates later callbacks', async () => {
  const first = deferred(), second = deferred(); let calls = 0
  const h = componentHarness({ createLink: async () => ++calls === 1 ? first.promise : second.promise })
  await h.mounted()
  h.props.studentId = 457
  await vue.nextTick()
  first.resolve(link()); await new Promise(setImmediate)
  assert.equal(h.api.state.value.link, null)
  h.api.close()
  second.resolve({ ...link(), student_id: 457 }); await new Promise(setImmediate)
  assert.equal(h.api.state.value.link, null)
  assert.deepEqual(h.events, ['close'])
  h.unmount()
})
test('unmounting before the mount tick avoids opening a detached dialog or making a request', async () => {
  let calls = 0
  const h = componentHarness({ createLink: async () => { calls++; return link() } })
  const mounting = h.mounted(); h.unmount(); await mounting
  assert.equal(calls, 0); assert.equal(h.opens(), 0)
})
test('copy failure offers manual fallback and a late copy result after closing is ignored', async () => {
  const pending = deferred(); let copyCalls = 0
  const h = componentHarness({ createLink: async () => link() }, { navigator: { clipboard: { writeText: async () => {
    if (++copyCalls === 1) throw Error('synthetic denied clipboard')
    return pending.promise
  } } } })
  await h.mounted(); await new Promise(setImmediate)
  await h.api.copyLink()
  assert.equal(h.api.copyError.value, true); assert.equal(h.api.copied.value, false)
  const copying = h.api.copyLink(); h.api.close(); pending.resolve(); await copying
  assert.equal(h.api.copied.value, false)
  h.unmount()
})
