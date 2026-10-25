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
const experience = compile(fs.readFileSync(path.join(__dirname, '../src/student/experience.ts'), 'utf8'), {});
const paperHelpers = compile(fs.readFileSync(path.join(__dirname, '../src/student/paperPrint.ts'), 'utf8'), { Blob, URL, Uint8Array });
function setup({ handheld = false } = {}) {
  experience.studentExperience.phonePrint = undefined;
  experience.studentExperience.mobileEntry = undefined;
  let routeUpdate;
  let consent = false;
  let listCalls = 0;
  const focused = [];
  const blobs = [], revoked = [];
  const device = { value: handheld };
  const api = { getAssignments: async () => { listCalls++; return { data: { data: [] } }; }, getBinding: async () => { throw Error('synthetic offline'); } };
  const source = fs.readFileSync(path.join(__dirname, '../src/views/StudentWorkspaceView.vue'), 'utf8').match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1];
  const exposed = '\nexport { mayDiscard, refreshAssignments, loadWorkspace, bindingRequired, error, uploader, activeAssignmentId, activeAssignment, submissionAssignment, assignments, selectedStudentId, showResult, clearResult, result, resultNotice, resultError, summaryVisible, openSubmit, closeSubmission, onSubmitted, notice, locateAssignment, highlightedAssignmentId, subject, status, search, effectiveAssignments, visibleAssignments, todos, reviews, reminders, createFamilyInvite, changeStudent, familyInviteCode, familyCode, familyNotice, familyError, printAssignment, openPhonePrint, paperAssignment, paperUrl, paperDialog, paperBusy, openPaper, closePaper, closePhonePrint, phonePrintButton, cardDetail, students, handheld, phonePrintAvailable, paperKind, paperInline, paperFilename, paperError, openMobileEntry, closeMobileEntry, mobileEntryStudentId, mobileEntryAvailable, mobileEntryButton, acceptedSubmissions };';
  const vue = { ref: value => ({ value }), computed: get => ({ get value() { return get(); } }), nextTick: async () => {}, onMounted: () => {}, onBeforeUnmount: () => {}, watch: () => {} };
  const view = compile(source + exposed, {
    window: { confirm: () => consent }, URL: { createObjectURL: blob => { blobs.push(blob); return `blob:synthetic-${blobs.length}`; }, revokeObjectURL: url => revoked.push(url) }, document: { getElementById: id => ({ focus: () => focused.push(id), scrollIntoView: () => {} }) },
    require: name => name === 'vue' ? vue : name === 'vue-router' ? { onBeforeRouteLeave: () => {}, onBeforeRouteUpdate: callback => { routeUpdate = callback; }, useRoute: () => ({ query: {} }) } : name === '@/stores/auth' ? { useAuthStore: () => ({ user: { role: 'student' } }) } : name === '@/api/student' ? { studentApi: api } : name === '@/student/workbench' ? helpers : name === '@/student/experience' ? experience : name === '@/student/device' ? { useStudentHandheld: () => device } : name === '@/student/paperPrint' ? paperHelpers : name === '@/api/paper' ? { paperApi: { studentMistakes: async () => ({ items: [] }) } } : {},
  });
  return { ...view, api, focused, experience, blobs, revoked, allow: () => { consent = true; }, calls: () => listCalls, routeUpdate: (to, from) => routeUpdate(to, from) };
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
    { id: 123, submitted: true, task_id: 'synthetic-existing', task_status: 'UNKNOWN_LAYOUT' },
    { id: 123, submitted: true, task_id: 'synthetic-existing', task_status: 'FAILED' },
  ]) {
    const h = setup(); await h.openSubmit(item);
    assert.equal(h.activeAssignmentId.value, null); assert.match(h.error.value, /原任务状态/);
  }
});

test('the workspace starts with unsubmitted assignments and reminder location selects the exact category', async () => {
  const h = setup();
  assert.equal(h.status.value, 'todo');
  h.assignments.value = [assignment(), { ...assignment('PENDING'), id: 124 }, { ...assignment(null), id: 125, submitted: false, task_id: null }];
  assert.deepEqual(Array.from(h.visibleAssignments.value, item => item.id), [125]);
  await h.locateAssignment(assignment());
  assert.equal(h.status.value, 'review');
  assert.deepEqual(Array.from(h.visibleAssignments.value, item => item.id), [123]);
  await h.locateAssignment({ ...assignment('FAILED'), id: 124 });
  assert.equal(h.status.value, 'submitted');
  assert.deepEqual(Array.from(h.visibleAssignments.value, item => item.id), [124]);
});

test('a failed progress read preserves the receipt and real category while showing retry guidance', async () => {
  for (const state of ['WAIT_REVIEW', 'HOLD_REVIEW', 'GRADING', 'FAILED', 'SUCCESS']) {
    const h = setup(); h.assignments.value = [assignment(state)];
    h.api.getStatus = async () => { throw Error('synthetic network unavailable'); };
    await h.showResult('synthetic-task');
    const item = h.effectiveAssignments.value[0];
    assert.equal(item.task_id, 'synthetic-task'); assert.equal(item.task_status, state);
    assert.equal(helpers.assignmentGroup(item), state.endsWith('REVIEW') ? 'review' : 'submitted');
    assert.match(h.cardDetail(item), /暂时无法读取.*原提交仍保留/);
    assert.equal(h.summaryVisible.value, false);
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
  h.subject.value = 'english'; h.status.value = 'submitted'; h.search.value = 'unrelated';
  h.activeAssignmentId.value = 999; h.uploader.value = { hasDraft: true, busy: false };
  await h.locateAssignment({ id: 123, subject: 'math', submitted: false });
  assert.equal(h.subject.value, ''); assert.equal(h.status.value, 'todo'); assert.equal(h.search.value, '');
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
  h.status.value = 'submitted'; assert.equal(h.visibleAssignments.value.length, 1);
  h.api.getStatus = async () => ({ data: { data: { status: 'SUCCESS' } } });
  h.api.getResult = async () => ({ data: { data: trustedFeedback } });
  await h.showResult('synthetic-task');
  assert.equal(h.effectiveAssignments.value[0].task_status, 'SUCCESS');
  h.status.value = 'submitted'; assert.equal(h.visibleAssignments.value.length, 1); assert.equal(h.summaryVisible.value, true);
});

test('SUCCESS with review feedback moves the assignment back to review everywhere until resolved', async () => {
  const h = setup(); h.assignments.value = [assignment('SUCCESS')];
  h.api.getStatus = async () => ({ data: { data: { status: 'SUCCESS' } } });
  h.api.getResult = async () => ({ data: { data: { total_score: 0, total_max_score: 5, results: [{ result: 'HOLD_REVIEW', score: 0, max_score: 5 }] } } });
  await h.showResult('synthetic-task');
  assert.equal(h.effectiveAssignments.value[0].task_status, 'HOLD_REVIEW'); assert.equal(h.reviews.value.length, 1);
  assert.equal(h.reminders.value.review.length, 1); h.status.value = 'submitted'; assert.equal(h.visibleAssignments.value.length, 0);
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
    assert.equal(helpers.assignmentGroup(item), 'submitted'); assert.equal(helpers.taskLabel(item.task_status), '状态待确认');
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

test('a lagging list cannot reopen a just-submitted assignment or discard its accepted task identifier', async () => {
  const h = setup(); h.selectedStudentId.value = 456;
  const todo = { ...assignment(), student_id: 456, task_id: null, submitted: false, task_status: null };
  h.assignments.value = [todo];
  h.api.getAssignments = async () => ({ data: { data: [{ ...todo }] } });
  await h.openSubmit(todo);
  await h.onSubmitted({ task_id: 'accepted-synthetic-task', status: 'PENDING', image_count: 3 });
  const item = h.assignments.value[0];
  assert.equal(item.submitted, true); assert.equal(item.task_id, 'accepted-synthetic-task');
  assert.equal(helpers.assignmentGroup(item), 'submitted'); assert.equal(h.todos.value.length, 0);
  assert.equal(h.submissionAssignment.value.task_id, 'accepted-synthetic-task');
  await h.openSubmit({ ...item, id: 123 });
  assert.equal(h.activeAssignmentId.value, 123);
  h.closeSubmission();
  await h.openSubmit(item);
  assert.equal(h.activeAssignmentId.value, null); assert.match(h.error.value, /原任务状态/);
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
  assert.equal(helpers.assignmentGroup(h.effectiveAssignments.value[0]), 'submitted');
});
test('family invitation data is cleared on identity switch and a late response is ignored', async () => {
  const h = setup(); h.selectedStudentId.value = 456; let finish;
  h.familyInviteCode.value = 'test-old-invite'; h.familyCode.value = 'test-typed-code';
  h.api.createFamilyInvite = () => new Promise(resolve => { finish = resolve; });
  const pending = h.createFamilyInvite();
  await h.changeStudent({ target: { value: '789' } });
  finish({ data: { data: { code: 'test-late-old-invite' } } }); await pending;
  assert.equal(h.familyInviteCode.value, ''); assert.equal(h.familyCode.value, ''); assert.equal(h.familyNotice.value, '');
});

const phoneTodo = () => ({ id: 123, student_id: 456, status: 'published', submitted: false, subject: 'math', title: '合成扫码作业' });
test('phone print remains available after submission or review and preserves the existing photo draft', () => {
  for (const taskStatus of ['WAIT_REVIEW', 'HOLD_REVIEW', 'SUCCESS']) {
    const h = setup();
    h.experience.studentExperience.phonePrint = { createLink: async () => {} };
    h.selectedStudentId.value = 456;
    const item = { ...phoneTodo(), assignment_mode: 'uniform_mixed', submitted: true, task_id: 'existing-task', task_status: taskStatus };
    h.assignments.value = [item];
    h.uploader.value = { hasDraft: true, busy: false }; h.activeAssignmentId.value = 999;
    h.openPhonePrint(item);
    assert.equal(h.printAssignment.value.id, 123); assert.equal(h.activeAssignmentId.value, 999);
    assert.equal(h.assignments.value[0], item); assert.equal(h.calls(), 0);
    assert.equal(h.notice.value, '');
  }
});
test('phone print rejects unbound, mismatched, unpublished or missing-original assignments without changing tasks', () => {
  const h = setup();
  h.experience.studentExperience.phonePrint = { createLink: async () => {} };
  const item = { ...phoneTodo(), assignment_mode: 'uniform_mixed' };
  h.openPhonePrint(item); assert.equal(h.printAssignment.value, null);
  h.selectedStudentId.value = 456;
  for (const changed of [{ ...item, student_id: 789 }, { ...item, status: 'draft' }, { ...item, assignment_mode: 'other' }]) {
    h.openPhonePrint(changed); assert.equal(h.printAssignment.value, null);
  }
  h.uploader.value = { hasDraft: true, busy: true };
  h.openPhonePrint(item); assert.equal(h.printAssignment.value, null); assert.match(h.error.value, /正在提交/);
  assert.equal(h.calls(), 0);
});

test('closing the nested printing QR preserves the original paper and restores its trigger focus', async () => {
  const h = setup(); let focused = 0, paperClosed = 0;
  const item = { ...phoneTodo(), assignment_mode: 'uniform_mixed' };
  h.selectedStudentId.value = 456;
  h.experience.studentExperience.phonePrint = { createLink: async () => {} };
  h.paperAssignment.value = item; h.paperUrl.value = 'blob:synthetic-paper';
  h.paperDialog.value = { open: true, close: () => { paperClosed++; } };
  h.phonePrintButton.value = { focus: () => { focused++; } };
  h.openPhonePrint(item); assert.equal(h.printAssignment.value.id, 123);
  await h.closePhonePrint();
  assert.equal(h.printAssignment.value, null); assert.equal(h.paperAssignment.value, item);
  assert.equal(h.paperUrl.value, 'blob:synthetic-paper'); assert.equal(paperClosed, 0);
  assert.equal(focused, 1); assert.equal(h.calls(), 0);
});

function paperSetup() {
  const h = setup({ handheld: true });
  h.selectedStudentId.value = 456;
  h.students.value = [{ student_id: 456, status: 'active', classes: [{ class_id: 41, status: 'active' }] }];
  const item = { ...phoneTodo(), class_id: 41, assignment_mode: 'uniform_mixed', original_format: 'pdf' };
  h.assignments.value = [item];
  return { h, item };
}
const syntheticPdf = () => new Blob(['%PDF-1.7\n合成试卷'], { type: 'application/pdf' });

test('handheld printing opens the authorized original directly without a QR provider or task changes', async () => {
  const { h, item } = paperSetup();
  let qrCalls = 0, sourceCalls = [];
  h.experience.studentExperience.phonePrint = { createLink: async () => { qrCalls++; } };
  h.api.getPublishedPaper = async (...args) => { sourceCalls.push(args); return { data: syntheticPdf() }; };
  h.uploader.value = { hasDraft: true, busy: false };
  assert.equal(h.phonePrintAvailable.value, false);
  h.openPhonePrint(item);
  assert.equal(h.printAssignment.value, null);
  await h.openPaper(item);
  assert.deepEqual(sourceCalls, [[123, 456]]);
  assert.equal(h.paperKind.value, 'pdf'); assert.equal(h.paperInline.value, true);
  assert.equal(h.paperFilename.value, item.title + '.pdf'); assert.ok(h.paperUrl.value);
  assert.equal(h.uploader.value.hasDraft, true); assert.equal(h.assignments.value[0], item);
  assert.equal(qrCalls, 0); assert.equal(h.calls(), 0);
});

test('handheld original viewer permits published review work and routes images or document formats safely', async () => {
  for (const entry of [
    { format: 'png', blob: new Blob([new Uint8Array([137,80,78,71,13,10,26,10])], { type: 'image/png' }), kind: 'image' },
    { format: 'docx', blob: new Blob(['synthetic Word document'], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }), kind: 'download' },
    { format: 'pdf', blob: new Blob(['<html>not a paper</html>'], { type: 'application/pdf' }), kind: 'download' },
  ]) {
    const { h, item } = paperSetup();
    Object.assign(item, { original_format: entry.format, submitted: true, task_id: 'existing-task', task_status: 'WAIT_REVIEW' });
    h.api.getPublishedPaper = async () => ({ data: entry.blob });
    await h.openPaper(item);
    assert.equal(h.paperKind.value, entry.kind); assert.equal(h.paperInline.value, entry.kind !== 'download');
    assert.equal(h.blobs[0].type, entry.kind === 'download' ? 'application/octet-stream' : 'image/png');
    assert.equal(item.task_status, 'WAIT_REVIEW');
  }
});

test('opening an original checks current account, active class and publication before any file request', async () => {
  for (const invalidate of [
    h => { h.selectedStudentId.value = 789; },
    h => { h.students.value = []; },
    h => { h.students.value[0].classes[0].status = 'inactive'; },
    h => { h.assignments.value[0].student_id = 789; },
    h => { h.assignments.value[0].status = 'draft'; },
    h => { h.assignments.value[0].assignment_mode = 'personalized'; },
    h => { h.assignments.value = []; },
  ]) {
    const { h, item } = paperSetup(); let sourceCalls = 0;
    h.api.getPublishedPaper = async () => { sourceCalls++; return { data: syntheticPdf() }; };
    invalidate(h); await h.openPaper(item);
    assert.equal(sourceCalls, 0); assert.ok(h.paperError.value); assert.equal(h.paperUrl.value, '');
  }
});

test('closing or replacing the mobile original ignores late files and releases the owned preview', async () => {
  const { h, item } = paperSetup(); let finish;
  h.api.getPublishedPaper = () => new Promise(resolve => { finish = resolve; });
  const pending = h.openPaper(item);
  h.closePaper(); finish({ data: syntheticPdf() }); await pending;
  assert.equal(h.paperUrl.value, ''); assert.equal(h.blobs.length, 0); assert.equal(h.paperBusy.value, false);
  h.api.getPublishedPaper = async () => ({ data: syntheticPdf() });
  await h.openPaper(item); const first = h.paperUrl.value;
  await h.openPaper(item);
  assert.deepEqual(h.revoked, [first]);
  h.closePaper(); assert.equal(h.revoked.length, 2);
});

test('a changed mobile identity or publication while loading never exposes a stale original', async () => {
  for (const changeIdentity of [true, false]) {
    const { h, item } = paperSetup(); let finish;
    h.api.getPublishedPaper = () => new Promise(resolve => { finish = resolve; });
    const pending = h.openPaper(item);
    if (changeIdentity) h.selectedStudentId.value = 789;
    else h.assignments.value[0].status = 'draft';
    finish({ data: syntheticPdf() }); await pending;
    assert.equal(h.paperUrl.value, ''); assert.ok(h.paperError.value); assert.equal(h.revoked.length, 1);
  }
});

test('mobile original failures clear old files, explain permissions or version issues, and allow retry', async () => {
  const { h, item } = paperSetup();
  h.api.getPublishedPaper = async () => ({ data: syntheticPdf() });
  await h.openPaper(item);
  for (const [status, message] of [[401, /登录已失效/], [403, /无权访问/], [404, /无权访问/], [409, /版本需老师核对/]]) {
    h.api.getPublishedPaper = async () => { throw { response: { status } }; };
    await h.openPaper(item);
    assert.equal(h.paperUrl.value, ''); assert.equal(h.paperBusy.value, false);
    assert.match(h.paperError.value, message);
    assert.equal(h.paperAssignment.value.id, item.id);
  }
  assert.equal(h.revoked.length, 1);
  h.api.getPublishedPaper = async () => ({ data: syntheticPdf() });
  await h.openPaper(h.paperAssignment.value);
  assert.ok(h.paperUrl.value); assert.equal(h.paperError.value, ''); assert.equal(h.paperKind.value, 'pdf');
});

const workspaceTodo = id => ({ id, student_id: 456, class_id: 11, class_name: '合成班级', title: `合成作业 ${id}`, subject: 'math', status: 'published', submitted: false, task_id: null, task_status: null });
function workspaceSetup(options) {
  const h = setup(options);
  h.selectedStudentId.value = 456;
  h.students.value = [{ student_id: 456, status: 'active', classes: [{ class_id: 11, status: 'active' }] }];
  h.experience.studentExperience.mobileEntry = { createLink: async () => {} };
  return h;
}

test('fixed mobile entry is read-only, preserves computer drafts and is scoped to the unique current child', async () => {
  const h = workspaceSetup(); const first = workspaceTodo(123);
  h.assignments.value = [first]; h.activeAssignmentId.value = 123;
  h.submissionAssignment.value = first;
  h.uploader.value = {hasDraft:true,busy:false,unresolved:true};
  h.openMobileEntry();
  assert.equal(h.mobileEntryStudentId.value,456); assert.equal(h.activeAssignmentId.value,123);
  assert.equal(h.submissionAssignment.value,first); assert.equal(h.assignments.value[0],first);
  assert.equal(h.calls(),0); assert.equal(h.notice.value,'');
  let focuses=0; h.mobileEntryButton.value={focus:()=>{focuses++;}};
  await h.closeMobileEntry(); assert.equal(h.mobileEntryStudentId.value,null); assert.equal(focuses,1);
  assert.equal(h.uploader.value.hasDraft,true);
  for(const change of [v=>{v.handheld.value=true;},v=>{v.selectedStudentId.value=789;},v=>{v.bindingRequired.value=true;},v=>{v.experience.studentExperience.mobileEntry=undefined;},v=>{v.uploader.value={hasDraft:true,busy:true};}]) {
    const bad=workspaceSetup(); change(bad); bad.openMobileEntry(); assert.equal(bad.mobileEntryStudentId.value,null); assert.equal(bad.calls(),0);
  }
});

test('closing the first receipt and opening a second assignment preserves the first accepted task against a lagging list', async () => {
  const h = workspaceSetup(); h.assignments.value = [workspaceTodo(123), workspaceTodo(124)];
  await h.openSubmit(h.assignments.value[0]);
  let finish;
  h.api.getAssignments = () => new Promise(resolve => { finish = resolve; });
  const first = h.onSubmitted({task_id:'accepted-first-task',status:'WAIT_REVIEW',image_count:9});
  h.closeSubmission(); await h.openSubmit(h.assignments.value[1]);
  finish({data:{data:[workspaceTodo(123),workspaceTodo(124)]}}); await first;
  assert.equal(h.activeAssignmentId.value, 124);
  assert.equal(h.assignments.value[0].task_id, 'accepted-first-task');
  assert.equal(h.assignments.value[0].submitted, true); assert.equal(h.todos.value.length, 1);
  h.api.getAssignments = async () => ({data:{data:[]}}); await h.refreshAssignments();
  h.api.getAssignments = async () => ({data:{data:[workspaceTodo(123)]}}); await h.refreshAssignments();
  assert.equal(h.assignments.value[0].task_id, 'accepted-first-task');
  h.selectedStudentId.value = 789;
  h.api.getAssignments = async () => ({data:{data:[{...workspaceTodo(123),student_id:789}]}}); await h.refreshAssignments();
  assert.equal(h.assignments.value[0].task_id, null);
});

test('a newer explicit server task supersedes a local receipt, and a later empty row never reopens it', async () => {
  const h=workspaceSetup(); h.assignments.value=[workspaceTodo(123)];
  await h.openSubmit(h.assignments.value[0]);
  await h.onSubmitted({task_id:'first',status:'WAIT_REVIEW',image_count:1});
  h.closeSubmission();
  h.api.getAssignments=async()=>({data:{data:[{...workspaceTodo(123),submitted:true,task_id:'server-newer',task_status:'GRADING'}]}});
  await h.refreshAssignments();
  h.api.getAssignments=async()=>({data:{data:[workspaceTodo(123)]}}); await h.refreshAssignments();
  assert.equal(h.assignments.value[0].task_id,'server-newer'); assert.equal(h.assignments.value[0].task_status,'GRADING');
  await h.changeStudent({target:{value:'789'}}); assert.equal(Object.keys(h.acceptedSubmissions.value).length,0);
});

test('switching the same student route to personal center protects photos and in-flight submissions', () => {
  const h = setup();
  const target = {query:{section:'profile'}}, from = {query:{}};
  h.uploader.value = {hasDraft:true,busy:false}; assert.equal(h.routeUpdate(target,from), false);
  h.allow(); assert.equal(h.routeUpdate(target,from), true);
  h.uploader.value.busy=true; assert.equal(h.routeUpdate(target,from), false);
  assert.equal(h.routeUpdate(from,from), true);
});

test('a fresh review state without a task field is never cleared by older local receipt evidence', async () => {
  const h=workspaceSetup(); h.assignments.value=[workspaceTodo(123)];
  await h.openSubmit(h.assignments.value[0]); await h.onSubmitted({task_id:'accepted-task',status:'SUCCESS',image_count:1});
  h.closeSubmission();
  h.api.getAssignments=async()=>({data:{data:[{...workspaceTodo(123),task_status:'HOLD_REVIEW'}]}}); await h.refreshAssignments();
  assert.equal(h.reviews.value.length,1); assert.equal(h.assignments.value[0].task_id,'accepted-task');
  h.api.getAssignments=async()=>({data:{data:[workspaceTodo(123)]}}); await h.refreshAssignments();
  assert.equal(h.reviews.value.length,1); assert.equal(h.summaryVisible.value,false);
});
