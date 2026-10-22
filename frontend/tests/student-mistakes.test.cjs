const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function setup() {
  const items = [
    { id: 1, student_id: 92001, subject: 'math', status: 'open', knowledge_points: ['方程'], created_at: '2026-10-22T08:00:00+08:00' },
    { id: 2, student_id: 92001, subject: 'english', status: 'pending', knowledge_points: [], created_at: '2026-10-21T08:00:00+08:00' },
    { id: 3, student_id: 92001, subject: 'math', status: 'correction_submitted', knowledge_points: ['方程'] },
    { id: 4, student_id: 92001, subject: 'math', status: 'mastered', knowledge_points: [] },
    { id: 5, student_id: 92001, subject: 'math', status: 'mastered_self_reported', knowledge_points: [] },
  ];
  let calls = 0;
  const paperApi = {
    studentMistakes: async id => { assert.equal(id, 92001); calls++; return { items: items.map(item => ({ ...item })) }; },
    submitCorrection: async (id, answer) => { assert.equal(answer, '合成订正过程'); items.find(item => item.id === id).status = 'correction_submitted'; },
  };
  const vue = { ref: value => ({ value }), computed: get => ({ get value() { return get(); } }), onMounted: () => {}, onBeforeUnmount: () => {} };
  const source = fs.readFileSync(path.join(__dirname, '../src/views/StudentMistakesView.vue'), 'utf8').match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1];
  const exposed = '\nexport { loadStudents, clearFilters, visibleMistakes, pendingCount, reviewCount, doneCount, subject, state, knowledge, dateFilter, drafts, selected, history, hasFilters, submitCorrection, notice, error };';
  const module = { exports: {} };
  vm.runInNewContext(ts.transpileModule(source + exposed, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText, {
    module, exports: module.exports, Set,
    require: name => name === 'vue' ? vue : name === 'vue-router' ? { onBeforeRouteLeave: () => {} } : name === '@/stores/auth' ? { useAuthStore: () => ({ user: { role: 'student' } }) } : name === '@/api/paper' ? { paperApi } : name === '@/api/student' ? { studentApi: { getMyStudents: async () => ({ data: { data: [{ student_id: 92001, name: '合成学生', status: 'active' }] } }) } } : {},
  });
  return { ...module.exports, paperApi, calls: () => calls };
}

test('mistakes start with actionable corrections while review and self reports stay distinct', async () => {
  const h = setup(); await h.loadStudents();
  assert.equal(h.state.value, 'todo');
  assert.deepEqual(Array.from(h.visibleMistakes.value, item => item.id), [1, 2]);
  assert.equal(h.pendingCount.value, 2); assert.equal(h.reviewCount.value, 1); assert.equal(h.doneCount.value, 1);
  h.state.value = 'review'; assert.deepEqual(Array.from(h.visibleMistakes.value, item => item.id), [3]);
  h.state.value = 'done'; assert.deepEqual(Array.from(h.visibleMistakes.value, item => item.id), [4]);
  h.state.value = 'all'; assert.equal(h.visibleMistakes.value.length, 5);
});

test('clearing conflicting mistake filters reveals all items without discarding drafts or review selections', async () => {
  const h = setup(); await h.loadStudents();
  h.subject.value = 'english'; h.knowledge.value = '方程'; h.dateFilter.value = '2026-10-22';
  h.drafts.value = { 1: '未提交的合成草稿' }; h.history.value = { 1: [{ status: 'submitted' }] }; h.selected.value.add(1);
  assert.equal(h.visibleMistakes.value.length, 0); const before = h.calls();
  h.clearFilters();
  assert.equal(h.hasFilters.value, false); assert.equal(h.visibleMistakes.value.length, 5);
  assert.equal(h.drafts.value[1], '未提交的合成草稿'); assert.equal(h.history.value[1][0].status, 'submitted'); assert.equal(h.selected.value.has(1), true);
  assert.equal(h.calls(), before);
});

test('successful correction moves to review and preserves other unfinished answers', async () => {
  const h = setup(); await h.loadStudents(); h.drafts.value = { 1: '  合成订正过程  ', 2: '另一道题的草稿' };
  await h.submitCorrection({ id: 1 });
  assert.equal(h.pendingCount.value, 1); assert.equal(h.reviewCount.value, 2);
  assert.deepEqual(Array.from(h.visibleMistakes.value, item => item.id), [2]);
  assert.equal(h.drafts.value[1], ''); assert.equal(h.drafts.value[2], '另一道题的草稿');
  assert.match(h.notice.value, /等待老师审核/);
  h.state.value = 'review'; assert.deepEqual(Array.from(h.visibleMistakes.value, item => item.id), [1, 3]);
});

test('failed correction keeps its draft and does not fabricate a reviewed state', async () => {
  const h = setup(); await h.loadStudents(); h.drafts.value = { 1: '合成订正过程' };
  h.paperApi.submitCorrection = async () => { throw { response: { data: { detail: '合成网络异常' } } }; };
  await h.submitCorrection({ id: 1 });
  assert.equal(h.drafts.value[1], '合成订正过程'); assert.equal(h.pendingCount.value, 2); assert.equal(h.reviewCount.value, 1);
  assert.equal(h.notice.value, ''); assert.match(h.error.value, /合成网络异常/);
});
