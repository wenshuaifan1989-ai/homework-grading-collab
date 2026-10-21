const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const moduleFixture = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/student/workbench.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText, { module: moduleFixture, exports: moduleFixture.exports, Date, Intl });
const h = moduleFixture.exports;
const row = (status, submitted = true) => ({ id: 1, title: 'synthetic', task_status: status, submitted });

test('review remains unresolved even when a stale submitted flag is false', () => {
  for (const state of ['WAIT_REVIEW', 'HOLD_REVIEW']) {
    assert.equal(h.assignmentGroup(row(state)), 'review');
    assert.equal(h.assignmentGroup(row(state, false)), 'review');
    assert.match(h.taskLabel(state), /复核/);
  }
  assert.equal(h.assignmentGroup(row('SUCCESS')), 'completed');
  assert.equal(h.assignmentGroup(row('FAILED')), 'attention');
  assert.equal(h.assignmentGroup(row('NEW_SERVER_STATE')), 'processing');
  assert.equal(h.assignmentGroup({ ...row('PENDING', false), task_id: 'synthetic-existing' }), 'processing');
  assert.equal(h.taskLabel('NEW_SERVER_STATE'), '状态待确认');
});
test('all nontrusted question states hide aggregate scores, including a false zero', () => {
  const confirmed = { result: 'correct', score: 0, max_score: 5 };
  assert.equal(h.trustedSummary({ results: [confirmed], total_score: 0, total_max_score: 5 }), true);
  for (const state of ['HOLD_REVIEW', 'WAIT_REVIEW', 'unknown', null]) {
    const pending = { result: state, score: 0, max_score: 5 };
    assert.equal(h.trustedQuestion(pending), false);
    assert.equal(h.trustedSummary({ results: [confirmed, pending], total_score: 0, total_max_score: 10 }), false);
    assert.equal(h.questionLabel(state), '等待老师核对');
  }
  assert.equal(h.trustedQuestion({ result: 'wrong', score: null, max_score: 5 }), false);
  assert.equal(h.trustedSummary({ results: [], total_score: 0, total_max_score: 0 }), false);
});
test('task priorities include older unsubmitted assignments and preserve source array', () => {
  const items = [row('SUCCESS'), row('WAIT_REVIEW'), { ...row(null, false), assignment_date: '2020-01-01' }];
  const sorted = h.sortAssignments(items);
  assert.equal(sorted[0].assignment_date, '2020-01-01');
  assert.equal(sorted[1].task_status, 'WAIT_REVIEW');
  assert.equal(items[0].task_status, 'SUCCESS');
});
test('only explicitly zoned deadlines are used to assert overdue', () => {
  assert.equal(h.deadlineTimestamp(null), null);
  assert.equal(h.deadlineTimestamp('2026-10-21T18:00:00'), null);
  assert.equal(h.deadlineTimestamp('invalid+08:00'), null);
  assert.equal(h.deadlineTimestamp('2026-10-21T18:00:00+08:00'), Date.parse('2026-10-21T10:00:00Z'));
  assert.match(h.dateLabel(null), /未设置/);
});
test('display labels distinguish self report, teacher review and acceptance', () => {
  assert.equal(h.subjectLabel('math'), '数学');
  assert.equal(h.gradeLabel('grade7'), '初一');
  assert.equal(h.mistakeLabel('correction_submitted'), '订正待老师审核');
  assert.equal(h.mistakeLabel('mastered_self_reported'), '已自评掌握');
  assert.equal(h.mistakeLabel('mastered'), '老师已审核');
  assert.equal(h.mistakeLabel('new-status'), '状态待确认');
});
test('reminders distinguish overdue work, future deadlines and reviews without inventing urgency', () => {
  const now = Date.parse('2026-10-21T10:00:00Z');
  const items = [
    { ...row(null, false), id: 1, due_at: '2026-10-21T17:00:00+08:00' },
    { ...row(null, false), id: 2, due_at: '2026-10-21T18:00:00+08:00' },
    { ...row(null, false), id: 3, due_at: '2026-10-22T18:00:00+08:00' },
    { ...row(null, false), id: 4, due_at: '2020-01-01T18:00:00' },
    { ...row(null, false), id: 5, due_at: null },
    { ...row('WAIT_REVIEW'), id: 6, due_at: '2026-10-21T16:00:00+08:00' },
    { ...row('FAILED'), id: 7, due_at: null },
    { ...row('NEW_STATE'), id: 8, due_at: '2026-10-21T16:00:00+08:00' },
    { ...row('SUCCESS'), id: 9, due_at: '2026-10-21T16:00:00+08:00' },
  ];
  const result = h.assignmentReminders(items, now);
  assert.deepEqual(Array.from(result.attention, item => item.id), [1, 7]);
  assert.deepEqual(Array.from(result.upcoming, item => item.id), [2, 3]);
  assert.deepEqual(Array.from(result.review, item => item.id), [6]);
  assert.equal(items[0].id, 1);
  assert.equal(items[3].due_at, '2020-01-01T18:00:00');
});
