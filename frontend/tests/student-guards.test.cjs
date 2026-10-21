const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
function compile(source, context) {
  const module = { exports: {} };
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText, { module, exports: module.exports, Date, Intl, Set, Math, ...context });
  return module.exports;
}
const helpers = compile(fs.readFileSync(path.join(__dirname, '../src/student/workbench.ts'), 'utf8'), {});
function setup() {
  let consent = false;
  let listCalls = 0;
  const api = { getAssignments: async () => { listCalls++; return { data: { data: [] } }; }, getBinding: async () => { throw Error('synthetic offline'); } };
  const source = fs.readFileSync(path.join(__dirname, '../src/views/StudentWorkspaceView.vue'), 'utf8').match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1];
  const exposed = '\nexport { mayDiscard, refreshAssignments, loadWorkspace, bindingRequired, error, uploader, activeAssignmentId, assignments, selectedStudentId, showResult, clearResult, result, resultNotice, summaryVisible, openSubmit };';
  const vue = { ref: value => ({ value }), computed: get => ({ get value() { return get(); } }), nextTick: async () => {}, onMounted: () => {}, onBeforeUnmount: () => {} };
  const view = compile(source + exposed, {
    window: { confirm: () => consent }, URL: { revokeObjectURL: () => {} },
    require: name => name === 'vue' ? vue : name === 'vue-router' ? { onBeforeRouteLeave: () => {} } : name === '@/stores/auth' ? { useAuthStore: () => ({ user: { role: 'student' } }) } : name === '@/api/student' ? { studentApi: api } : name === '@/student/workbench' ? helpers : name === '@/api/paper' ? { paperApi: { studentMistakes: async () => ({ items: [] }) } } : {},
  });
  return { ...view, api, allow: () => { consent = true; }, calls: () => listCalls };
}
test('cancelled refresh/navigation preserves photos and the selected assignment', async () => {
  const h = setup(); h.uploader.value = { hasDraft: true, busy: false }; h.activeAssignmentId.value = 123;
  assert.equal(h.mayDiscard(), false); await h.refreshAssignments();
  assert.equal(h.activeAssignmentId.value, 123); assert.equal(h.calls(), 0);
  h.allow(); h.selectedStudentId.value = 456; await h.refreshAssignments();
  assert.equal(h.activeAssignmentId.value, null); assert.equal(h.calls(), 1);
});
test('in-flight submission blocks switching and shows a useful message', () => {
  const h = setup(); h.uploader.value = { hasDraft: true, busy: true }; h.allow();
  assert.equal(h.mayDiscard(), false); assert.match(h.error.value, /正在提交/);
});
test('a stale submitted flag cannot reopen an existing or review task for upload', async () => {
  for (const item of [
    { id: 123, submitted: false, task_status: 'WAIT_REVIEW' },
    { id: 123, submitted: false, task_status: 'HOLD_REVIEW' },
    { id: 123, submitted: false, task_id: 'synthetic-existing', task_status: 'PENDING' },
  ]) {
    const h = setup(); await h.openSubmit(item);
    assert.equal(h.activeAssignmentId.value, null); assert.match(h.error.value, /原任务状态/);
  }
});
test('identity transport failure does not falsely claim the student is unbound', async () => {
  const h = setup(); await h.loadWorkspace();
  assert.equal(h.bindingRequired.value, false); assert.ok(h.error.value); assert.equal(h.calls(), 0);
});
test('WAIT_REVIEW and HOLD_REVIEW do not request grading results', async () => {
  for (const status of ['WAIT_REVIEW', 'HOLD_REVIEW']) {
    const h = setup(); let resultRequests = 0;
    h.api.getStatus = async () => ({ data: { data: { status } } });
    h.api.getResult = async () => { resultRequests++; throw Error('must not fetch'); };
    await h.showResult('synthetic-task');
    assert.equal(resultRequests, 0); assert.equal(h.result.value, null); assert.match(h.resultNotice.value, /不显示分数/);
  }
});
test('SUCCESS with a pending question hides aggregate scores', async () => {
  const h = setup(); h.api.getStatus = async () => ({ data: { data: { status: 'SUCCESS' } } });
  h.api.getResult = async () => ({ data: { data: { total_score: 0, total_max_score: 5, results: [{ result: 'HOLD_REVIEW', score: 0, max_score: 5 }] } } });
  await h.showResult('synthetic-task'); assert.equal(h.summaryVisible.value, false); assert.match(h.resultNotice.value, /暂不展示总分/);
});
test('cleared identity/result context ignores a late response', async () => {
  const h = setup(); let finish;
  h.api.getStatus = () => new Promise(resolve => { finish = resolve; });
  const request = h.showResult('old-task'); h.clearResult(); finish({ data: { data: { status: 'WAIT_REVIEW' } } });
  await request; assert.equal(h.result.value, null); assert.equal(h.resultNotice.value, '');
});
