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
  assert.equal(h.assignmentGroup(row('SUCCESS')), 'submitted');
  assert.equal(h.assignmentGroup(row('FAILED')), 'submitted');
  assert.equal(h.assignmentGroup(row('NEW_SERVER_STATE')), 'submitted');
  assert.equal(h.assignmentGroup({ ...row('PENDING', false), task_id: 'synthetic-existing' }), 'submitted');
  assert.equal(h.taskLabel('NEW_SERVER_STATE'), '状态待确认');
});

test('only three assignment categories are offered and receipts are distinct from trusted feedback', () => {
  assert.deepEqual(Array.from(h.assignmentFilters, item => `${item.value}:${item.label}`), ['todo:待提交', 'submitted:已提交', 'review:待复核']);
  assert.equal(h.assignmentGroupLabel(row(null, false)), '待提交');
  for (const state of ['PENDING', 'PREPROCESSING', 'PROCESSING', 'GRADING', 'SUCCESS', 'FAILED', 'CANCELLED', 'UNKNOWN_LAYOUT', 'future-state', null]) {
    const item = row(state);
    assert.equal(h.assignmentGroupLabel(item), '已提交');
    assert.doesNotMatch(h.assignmentDetail(item), /批改已完成|0分|零分/);
  }
  for (const state of ['PENDING', 'PREPROCESSING', 'PROCESSING', 'GRADING', 'RESULT_PENDING'])
    assert.match(h.assignmentDetail(row(state)), /老师加紧批改中/);
  assert.match(h.assignmentDetail(row('SUCCESS')), /已收到处理结果状态/);
  assert.doesNotMatch(h.assignmentDetail(row('SUCCESS')), /老师加紧批改中|批改已完成/);
  assert.match(h.assignmentDetail(row('SUCCESS'), true), /反馈已核对/);
  assert.match(h.assignmentDetail(row('FAILED')), /未完成/);
  assert.match(h.assignmentDetail(row('CANCELLED')), /已取消/);
  assert.match(h.assignmentDetail(row('UNKNOWN_LAYOUT')), /核对/);
  assert.match(h.assignmentDetail(row('future-state')), /状态待确认/);
  assert.match(h.assignmentDetail(row(null)), /状态待确认/);
});

test('each category sorts its own reliable dates and leaves missing-date positions unchanged', () => {
  const date = day => `2026-10-${day}T10:00:00+08:00`;
  const cases = [
    ['todo', null, false, 'due_at', [3, 2, 5, 4, 1]],
    ['submitted', 'GRADING', true, 'submitted_at', [1, 2, 5, 4, 3]],
    ['review', 'WAIT_REVIEW', true, 'submitted_at', [3, 2, 5, 4, 1]],
  ];
  for (const [group, state, submitted, field, expected] of cases) {
    const items = [
      { ...row(state, submitted), id: 1, [field]: date(24) },
      { ...row(state, submitted), id: 2 },
      { ...row(state, submitted), id: 3, [field]: date(22) },
      { ...row(state, submitted), id: 4, [field]: '2026-10-21T10:00:00' },
      { ...row(state, submitted), id: 5, [field]: date(23) },
    ];
    assert.equal(h.assignmentGroup(items[0]), group);
    assert.deepEqual(Array.from(h.sortAssignments(items), item => item.id), expected);
    assert.deepEqual(items.map(item => item.id), [1, 2, 3, 4, 5]);
  }
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
  assert.equal(sorted[1].task_status, 'SUCCESS');
  assert.equal(sorted[2].task_status, 'WAIT_REVIEW');
  assert.equal(items[0].task_status, 'SUCCESS');
});
test('only explicitly zoned deadlines are used to assert overdue', () => {
  assert.equal(h.deadlineTimestamp(null), null);
  assert.equal(h.deadlineTimestamp('2026-10-21T18:00:00'), null);
  assert.equal(h.deadlineTimestamp('invalid+08:00'), null);
  assert.equal(h.deadlineTimestamp('2026-10-21T18:00:00+08:00'), Date.parse('2026-10-21T10:00:00Z'));
  assert.match(h.dateLabel(null), /未设置/);
});
test('relative deadline hints use Shanghai calendar days and keep the exact cutoff', () => {
  const now = Date.parse('2026-10-22T15:30:00Z'); // 23:30 in Shanghai
  assert.equal(h.deadlineHint('2026-10-22T23:29:59+08:00', now), '已过截止');
  assert.equal(h.deadlineHint('2026-10-22T23:30:00+08:00', now), '今天截止');
  assert.equal(h.deadlineHint('2026-10-22T15:59:00Z', now), '今天截止');
  assert.equal(h.deadlineHint('2026-10-22T16:00:00Z', now), '明天截止');
  assert.equal(h.deadlineHint('2026-10-23T23:59:59+08:00', now), '明天截止');
  assert.equal(h.deadlineHint('2026-10-24T00:00:00+08:00', now), '');
  assert.equal(h.deadlineHint('2027-01-01T00:00:00+08:00', Date.parse('2026-12-31T23:00:00+08:00')), '明天截止');
});
test('relative deadline hints never infer missing, invalid or unzoned dates', () => {
  for (const value of [null, undefined, '', '2026-10-22T10:00:00', 'invalid+08:00']) {
    assert.equal(h.deadlineHint(value, Date.parse('2026-10-22T09:00:00+08:00')), '');
  }
  assert.equal(h.deadlineHint('2026-10-22T10:00:00+08:00', NaN), '');
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
  assert.deepEqual(Array.from(result.overdue, item => item.id), [1]);
  assert.deepEqual(Array.from(result.upcoming, item => item.id), [2, 3]);
  assert.deepEqual(Array.from(result.review, item => item.id), [6]);
  assert.equal(items[0].id, 1);
  assert.equal(items[3].due_at, '2020-01-01T18:00:00');
});
