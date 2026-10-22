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
  const focused = [];
  const api = { getAssignments: async () => { listCalls++; return { data: { data: [] } }; }, getBinding: async () => { throw Error('synthetic offline'); } };
  const source = fs.readFileSync(path.join(__dirname, '../src/views/StudentWorkspaceView.vue'), 'utf8').match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1];
  const exposed = '\nexport { mayDiscard, refreshAssignments, loadWorkspace, bindingRequired, error, uploader, activeAssignmentId, activeAssignment, submissionAssignment, assignments, selectedStudentId, showResult, clearResult, result, resultNotice, resultError, summaryVisible, openSubmit, closeSubmission, onSubmitted, notice, locateAssignment, highlightedAssignmentId, subject, status, search, effectiveAssignments, visibleAssignments, todos, reviews, reminders };';
  const vue = { ref: value => ({ value }), computed: get => ({ get value() { return get(); } }), nextTick: async () => {}, onMounted: () => {}, onBeforeUnmount: () => {} };
  const view = compile(source + exposed, {
    window: { confirm: () => consent }, URL: { revokeObjectURL: () => {} }, document: { getElementById: id => ({ focus: () => focused.push(id), scrollIntoView: () => {} }) },
    require: name => name === 'vue' ? vue : name === 'vue-router' ? { onBeforeRouteLeave: () => {} } : name === '@/stores/auth' ? { useAuthStore: () => ({ user: { role: 'student' } }) } : name === '@/api/student' ? { studentApi: api } : name === '@/student/workbench' ? helpers : name === '@/api/paper' ? { paperApi: { studentMistakes: async () => ({ items: [] }) } } : {},
  });
  return { ...view, api, focused, allow: () => { consent = true; }, calls: () => listCalls };
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
test('opening another assignment for submission clears feedback from the previous task', async () => {
  const h = setup();
  h.result.value = { total_score: 7, total_max_score: 10, results: [] };
  await h.openSubmit({ id: 123, submitted: false, subject: 'math' });
  assert.equal(h.activeAssignmentId.value, 123);
  assert.equal(h.result.value, null);
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
test('reminder location clears conflicting filters, focuses the exact assignment and preserves queued photos', async () => {
  const h = setup();
  h.selectedStudentId.value = 456;
  h.subject.value = 'english'; h.status.value = 'completed'; h.search.value = 'unrelated';
  h.activeAssignmentId.value = 999; h.uploader.value = { hasDraft: true, busy: false };
  await h.locateAssignment({ id: 123, subject: 'math', submitted: false });
  assert.equal(h.subject.value, ''); assert.equal(h.status.value, 'all'); assert.equal(h.search.value, '');
  assert.equal(h.highlightedAssignmentId.value, 123);
  assert.deepEqual(h.focused, ['assignment-123']);
  assert.equal(h.activeAssignmentId.value, 999);
  assert.equal(h.uploader.value.hasDraft, true);
  assert.equal(h.calls(), 0);
});
test('reminder navigation does not focus a previous student assignment after identity changes', async () => {
  const h = setup(); h.selectedStudentId.value = 456;
  const request = h.locateAssignment({ id: 123 });
  h.selectedStudentId.value = 789;
  await request;
  assert.deepEqual(h.focused, []);
});

const assignment = (task_status = 'WAIT_REVIEW') => ({ id: 123, subject: 'math', title: '合成作业', class_name: '合成班级', submitted: true, task_id: 'synthetic-task', task_status });
const trustedFeedback = { total_score: 4, total_max_score: 5, results: [{ result: 'partial', score: 4, max_score: 5 }] };
test('fresh status synchronizes cards, filters and reminders, including release from review', async () => {
  const h = setup(); h.assignments.value = [assignment()]; h.status.value = 'review';
  h.api.getStatus = async () => ({ data: { data: { status: 'GRADING' } } });
  await h.showResult('synthetic-task');
  assert.equal(h.effectiveAssignments.value[0].task_status, 'GRADING');
  assert.equal(h.reviews.value.length, 0); assert.equal(h.reminders.value.review.length, 0); assert.equal(h.visibleAssignments.value.length, 0);
  h.status.value = 'processing'; assert.equal(h.visibleAssignments.value.length, 1);
  h.api.getStatus = async () => ({ data: { data: { status: 'SUCCESS' } } });
  h.api.getResult = async () => ({ data: { data: trustedFeedback } });
  await h.showResult('synthetic-task');
  assert.equal(h.effectiveAssignments.value[0].task_status, 'SUCCESS');
  h.status.value = 'completed'; assert.equal(h.visibleAssignments.value.length, 1); assert.equal(h.summaryVisible.value, true);
});

test('SUCCESS with review feedback moves the assignment back to review everywhere until resolved', async () => {
  const h = setup(); h.assignments.value = [assignment('SUCCESS')];
  h.api.getStatus = async () => ({ data: { data: { status: 'SUCCESS' } } });
  h.api.getResult = async () => ({ data: { data: { total_score: 0, total_max_score: 5, results: [{ result: 'HOLD_REVIEW', score: 0, max_score: 5 }] } } });
  await h.showResult('synthetic-task');
  assert.equal(h.effectiveAssignments.value[0].task_status, 'HOLD_REVIEW'); assert.equal(h.reviews.value.length, 1);
  assert.equal(h.reminders.value.review.length, 1); h.status.value = 'completed'; assert.equal(h.visibleAssignments.value.length, 0);
  h.api.getResult = async () => ({ data: { data: trustedFeedback } });
  await h.showResult('synthetic-task'); assert.equal(h.reviews.value.length, 0); assert.equal(h.visibleAssignments.value.length, 1);
});

test('SUCCESS without feedback does not claim completion or preserve a false review label', async () => {
  for (const fail of [false, true]) {
    const h = setup(); h.assignments.value = [assignment()];
    h.api.getStatus = async () => ({ data: { data: { status: 'SUCCESS' } } });
    h.api.getResult = async () => { if (fail) throw Error('synthetic offline'); return { data: { data: { results: [] } } }; };
    await h.showResult('synthetic-task');
    const item = h.effectiveAssignments.value[0];
    assert.equal(helpers.assignmentGroup(item), 'processing'); assert.equal(helpers.taskLabel(item.task_status), '状态待确认');
    assert.equal(h.reviews.value.length, 0); assert.equal(h.summaryVisible.value, false); assert.equal(h.result.value, null);
  }
});

test('late result cannot change a new identity or an assignment whose task has been replaced', async () => {
  for (const identityChanged of [false, true]) {
    const h = setup(); h.assignments.value = [assignment()]; h.selectedStudentId.value = 456;
    let finish;
    h.api.getStatus = () => new Promise(resolve => { finish = resolve; });
    const pending = h.showResult('synthetic-task');
    if (identityChanged) h.selectedStudentId.value = 789;
    else h.assignments.value = [{ ...assignment(), task_id: 'synthetic-new-task', task_status: 'GRADING' }];
    finish({ data: { data: { status: 'FAILED' } } }); await pending;
    assert.notEqual(h.effectiveAssignments.value[0].task_status, 'FAILED'); assert.equal(h.resultNotice.value, '');
  }
});

test('late SUCCESS feedback cannot mark an assignment complete after identity switches', async () => {
  const h = setup(); h.assignments.value = [assignment()]; h.selectedStudentId.value = 456;
  let finish, started;
  const requested = new Promise(resolve => { started = resolve; });
  h.api.getStatus = async () => ({ data: { data: { status: 'SUCCESS' } } });
  h.api.getResult = () => new Promise(resolve => { finish = resolve; started(); });
  const pending = h.showResult('synthetic-task'); await requested;
  h.selectedStudentId.value = 789;
  finish({ data: { data: trustedFeedback } }); await pending;
  assert.equal(h.result.value, null); assert.notEqual(h.effectiveAssignments.value[0].task_status, 'SUCCESS');
});

test('closing a submission uses the same draft and busy protections as leaving the page', async () => {
  const h = setup(); await h.openSubmit({ ...assignment(), task_id: null, submitted: false, task_status: null });
  h.uploader.value = { hasDraft: true, busy: false }; h.closeSubmission();
  assert.equal(h.activeAssignmentId.value, 123); assert.ok(h.submissionAssignment.value);
  h.allow(); h.uploader.value.busy = true; h.closeSubmission(); assert.equal(h.activeAssignmentId.value, 123);
  h.uploader.value.busy = false; h.closeSubmission(); assert.equal(h.activeAssignmentId.value, null); assert.equal(h.submissionAssignment.value, null);
});

test('successful submission keeps its receipt context even if the following list omits the assignment', async () => {
  const h = setup(); h.selectedStudentId.value = 456;
  await h.openSubmit({ ...assignment(), task_id: null, submitted: false, task_status: null });
  await h.onSubmitted({ task_id: 'synthetic-receipt', status: 'WAIT_REVIEW', image_count: 2 });
  assert.equal(h.activeAssignmentId.value, 123); assert.equal(h.activeAssignment.value.task_id, 'synthetic-receipt');
  assert.match(h.notice.value, /2 张照片/); assert.match(h.notice.value, /synthetic-receipt/);
  h.closeSubmission(); assert.equal(h.activeAssignmentId.value, null);
});

test('a newer list supersedes old processing or review observations without pretending SUCCESS feedback is verified', async () => {
  const h = setup(); h.selectedStudentId.value = 456; h.assignments.value = [assignment()];
  h.api.getStatus = async () => ({ data: { data: { status: 'GRADING' } } });
  await h.showResult('synthetic-task');
  h.api.getAssignments = async () => ({ data: { data: [assignment('WAIT_REVIEW')] } });
  await h.refreshAssignments(); assert.equal(h.effectiveAssignments.value[0].task_status, 'WAIT_REVIEW'); assert.equal(h.reviews.value.length, 1);
  assert.equal(h.resultNotice.value, '', 'the old processing message must not contradict the refreshed review card');
  h.api.getStatus = async () => ({ data: { data: { status: 'HOLD_REVIEW' } } });
  await h.showResult('synthetic-task');
  h.api.getAssignments = async () => ({ data: { data: [assignment('GRADING')] } });
  await h.refreshAssignments(); assert.equal(h.effectiveAssignments.value[0].task_status, 'GRADING'); assert.equal(h.reviews.value.length, 0);
  // The most recent list now supplies the display status rather than a sticky old override.
  h.api.getAssignments = async () => ({ data: { data: [assignment('FAILED')] } });
  await h.refreshAssignments(); assert.equal(h.effectiveAssignments.value[0].task_status, 'FAILED');
});

test('a list SUCCESS cannot silently erase previously unverified question feedback', async () => {
  const h = setup(); h.selectedStudentId.value = 456; h.assignments.value = [assignment()];
  h.api.getStatus = async () => ({ data: { data: { status: 'SUCCESS' } } });
  h.api.getResult = async () => ({ data: { data: { results: [{ result: 'HOLD_REVIEW', score: 0, max_score: 5 }] } } });
  await h.showResult('synthetic-task');
  h.api.getAssignments = async () => ({ data: { data: [assignment('SUCCESS')] } });
  await h.refreshAssignments();
  assert.equal(helpers.taskLabel(h.effectiveAssignments.value[0].task_status), '状态待确认'); assert.equal(h.summaryVisible.value, false);
  h.api.getResult = async () => ({ data: { data: trustedFeedback } });
  await h.showResult('synthetic-task'); assert.equal(h.effectiveAssignments.value[0].task_status, 'SUCCESS');
});

test('an older in-flight list cannot overwrite a more recent explicit status observation', async () => {
  const h = setup(); h.selectedStudentId.value = 456; h.assignments.value = [assignment('GRADING')];
  let finish;
  h.api.getAssignments = () => new Promise(resolve => { finish = resolve; });
  const pending = h.refreshAssignments();
  h.api.getStatus = async () => ({ data: { data: { status: 'WAIT_REVIEW' } } });
  await h.showResult('synthetic-task');
  finish({ data: { data: [assignment('GRADING')] } }); await pending;
  assert.equal(h.effectiveAssignments.value[0].task_status, 'WAIT_REVIEW'); assert.equal(h.reviews.value.length, 1);
});

test('a fresh list returning review invalidates previously displayed completed scores', async () => {
  const h = setup(); h.selectedStudentId.value = 456; h.assignments.value = [assignment()];
  h.api.getStatus = async () => ({ data: { data: { status: 'SUCCESS' } } });
  h.api.getResult = async () => ({ data: { data: trustedFeedback } });
  await h.showResult('synthetic-task'); assert.equal(h.summaryVisible.value, true);
  h.api.getAssignments = async () => ({ data: { data: [assignment('HOLD_REVIEW')] } });
  await h.refreshAssignments(); assert.equal(h.summaryVisible.value, false); assert.equal(h.result.value, null);
  assert.equal(h.effectiveAssignments.value[0].task_status, 'HOLD_REVIEW');
});

test('a missing status is shown as unconfirmed instead of an unsubmitted task', async () => {
  const h = setup(); h.assignments.value = [assignment()];
  h.api.getStatus = async () => ({ data: { data: {} } });
  await h.showResult('synthetic-task');
  assert.match(h.resultNotice.value, /状态待确认/); assert.doesNotMatch(h.resultNotice.value, /待提交/);
  assert.equal(helpers.assignmentGroup(h.effectiveAssignments.value[0]), 'processing');
});
