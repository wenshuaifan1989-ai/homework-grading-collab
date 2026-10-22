const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
function compile(source, context = {}) {
  const module = { exports: {} };
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText, { module, exports: module.exports, ...context });
  return module.exports;
}
const helpers = compile(fs.readFileSync(path.join(__dirname, '../src/student/profile.ts'), 'utf8'));
const student = () => ({ student_id: 92001, name: '合成学生', relationship_type: 'self', status: 'active', classes: [{ class_id: 93001, class_name: '合成班级', status: 'active' }] });
const bound = () => ({ is_bound: true, student_id: 92001, roster_id: 94001, student_no: 'SYN-001', class_id: 93001, class_name: '合成班级' });
function setup() {
  const props = { account: { id: 91001, role: 'student', username: 'synthetic_student' }, student: student(), metrics: [] };
  const api = { getBinding: async () => ({ data: { data: bound() } }) };
  const source = fs.readFileSync(path.join(__dirname, '../src/components/student/StudentProfilePanel.vue'), 'utf8').match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1];
  const exposed = '\nexport { loadBinding, binding, bindingState, identity, dialog, openProfile, closeProfile };';
  const vue = { ref: value => ({ value }), computed: get => ({ get value() { return get(); } }), watch: () => {}, onBeforeUnmount: () => {} };
  const view = compile(source + exposed, { defineProps: () => props, require: name => name === 'vue' ? vue : name === '@/api/student' ? { studentApi: api } : name === '@/student/profile' ? helpers : {} });
  view.dialog.value = { open: false, showModal() { this.open = true; }, close() { this.open = false; } };
  return { ...view, props, api };
}

test('profile contacts are masked, including accounts that use a phone or email as username', () => {
  assert.equal(helpers.maskedPhone('+1 (202) 555-0100'), '120****0100');
  assert.equal(helpers.maskedPhone('555-0100'), '5****00');
  assert.equal(helpers.maskedPhone('123'), '已提供（已隐藏）');
  assert.equal(helpers.maskedEmail('student@example.invalid'), 's***@example.invalid');
  assert.equal(helpers.accountName('student@example.invalid'), 's***@example.invalid');
  assert.equal(helpers.accountName('+1 (202) 555-0100'), '120****0100');
  assert.equal(helpers.accountName('synthetic_student'), 'synthetic_student');
  assert.equal(helpers.maskedPhone(null), '当前资料未提供');
  assert.equal(helpers.maskedEmail('invalid'), '已提供（已隐藏）');
});

test('student number requires matching Student.id and active class, never User.id or Roster.id', () => {
  assert.equal(helpers.profileBinding(student(), bound(), 'ready').studentNo, 'SYN-001');
  for (const studentId of [91001, 94001]) {
    const value = helpers.profileBinding(student(), { ...bound(), student_id: studentId }, 'ready');
    assert.equal(value.studentNo, null); assert.equal(value.className, null); assert.match(value.message, /不一致/);
  }
  assert.equal(helpers.profileBinding(student(), { ...bound(), class_id: 93002 }, 'ready').studentNo, null);
  const former = student(); former.classes[0].status = 'inactive';
  assert.equal(helpers.profileBinding(former, bound(), 'ready').studentNo, null);
});

test('unavailable profile data is not described as unbound or fabricated from another identity', () => {
  for (const state of ['loading', 'error', 'idle', 'not_applicable']) {
    const value = helpers.profileBinding(student(), bound(), state);
    assert.equal(value.studentNo, null); assert.doesNotMatch(value.message, /尚未完成.*绑定/);
  }
  assert.match(helpers.profileBinding(student(), { is_bound: false }, 'ready').message, /尚未完成/);
  assert.equal(helpers.profileBinding(null, bound(), 'ready').studentNo, null);
  assert.match(helpers.profileBinding(student(), null, 'ready').message, /尚未确认/);
  assert.equal(helpers.relationshipLabel({ ...student(), relationship_type: 'father' }), '父亲');
});

test('profile binding failure can be retried without claiming the student is unbound', async () => {
  const h = setup(); h.api.getBinding = async () => { throw Error('synthetic offline'); };
  await h.loadBinding(); assert.equal(h.bindingState.value, 'error'); assert.equal(h.identity.value.studentNo, null);
  h.api.getBinding = async () => ({ data: { data: bound() } });
  await h.loadBinding(); assert.equal(h.identity.value.studentNo, 'SYN-001');
});

test('a late binding response cannot leak the previous student number into a new selected identity', async () => {
  const h = setup(); let finish;
  h.api.getBinding = () => new Promise(resolve => { finish = resolve; });
  const previous = h.loadBinding(); h.props.student = { ...student(), student_id: 92002, name: '另一合成学生' };
  h.api.getBinding = async () => ({ data: { data: { ...bound(), student_id: 92002, student_no: 'SYN-002' } } });
  await h.loadBinding(); finish({ data: { data: bound() } }); await previous;
  assert.equal(h.identity.value.studentNo, 'SYN-002'); assert.equal(h.binding.value.student_id, 92002);
});

test('closing a profile cancels its pending binding result; family access does not request self-binding', async () => {
  const h = setup(); let finish;
  h.api.getBinding = () => new Promise(resolve => { finish = resolve; });
  const pending = h.loadBinding(); h.dialog.value.open = true; h.closeProfile();
  finish({ data: { data: bound() } }); await pending;
  assert.equal(h.binding.value, null); assert.equal(h.bindingState.value, 'idle');
  h.props.account.role = 'teacher'; h.props.student.relationship_type = 'father';
  h.api.getBinding = async () => { throw Error('must not request student self-binding'); };
  await h.loadBinding(); assert.equal(h.bindingState.value, 'not_applicable'); assert.equal(h.identity.value.studentNo, null);
  h.props.disabled = true; h.openProfile(); assert.equal(h.dialog.value.open, false);
});
