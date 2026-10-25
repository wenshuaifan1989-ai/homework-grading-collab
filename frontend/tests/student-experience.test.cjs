const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const root = path.resolve(__dirname, '..')
function compile(source, requireMock = () => ({}), other = {}) {
  const module = { exports: {} }
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText,
    { module, exports: module.exports, require: requireMock, Set, Map, Date, Math, ...other })
  return module.exports
}
const experience = compile(fs.readFileSync(path.join(root, 'src/student/experience.ts'), 'utf8'))
const profile = compile(fs.readFileSync(path.join(root, 'src/student/profile.ts'), 'utf8'))
const student = () => ({ student_id: 92001, name: '不可显示的合成姓名', relationship_type: 'father', status: 'active', classes: [{ class_id: 93001, class_name: '合成一班', status: 'active' }] })
const binding = () => ({ is_bound: true, student_id: 92001, class_id: 93001, student_no: 'SYN-001' })
test('one account may have repeated links to the same child but never silently chooses between two children', () => {
  const a = student()
  assert.equal(experience.singleStudent([a, { ...a, relationship_type: 'guardian' }]).student_id, 92001)
  assert.equal(experience.singleStudent([a, { ...a, student_id: 92002 }]), null)
  assert.match(experience.identityIssue([a, { ...a, student_id: 92002 }]), /多个学生/)
})
test('missing assignment IDs do not combine unrelated mistakes; empty subject never displays mixed subjects', () => {
  const items = [{ id: 1, assignment_id: 0, subject: 'math' }, { id: 2, assignment_id: 0, subject: 'math' }, { id: 3, assignment_id: 8, subject: 'english' }]
  assert.equal(experience.assignmentMistakes(items, '').length, 0)
  assert.equal(experience.assignmentMistakes(items, 'math').length, 2)
  assert.equal(experience.assignmentMistakes(items, 'english').length, 1)
})
function personalHarness() {
  const props = { account: { phone: '123-4567' }, student: student(), binding: binding() }
  const service = { ...experience.studentExperience }
  const vue = { ref: value => ({ value }), computed: get => ({ get value() { return get() } }), watch: () => {}, onBeforeUnmount: () => {} }
  const source = fs.readFileSync(path.join(root, 'src/components/student/StudentPersonalCenter.vue'), 'utf8').match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1]
  const exposed = '\nexport { reload, details, relatives, loading, identityError, familyError, verified, className };'
  const view = compile(source + exposed, name => name === 'vue' ? vue : name === '@/student/profile' ? profile : name === '@/student/experience' ? { studentExperience: service } : {}, { defineProps: () => props })
  return { ...view, props, service }
}
test('personal center accepts only the same student and active class, with a separate sequence', async () => {
  const h = personalHarness()
  h.service.identity = async () => ({ student_id: 92001, school_name: '合成学校', class_id: 93001, class_name: '合成一班', student_no: 'SYN-001', student_sequence: '07' })
  h.service.relatives = async () => [{ relationship_type: 'mother', masked_phone: '139****0002', is_current: false }]
  await h.reload()
  assert.equal(h.details.value.student_sequence, '07')
  assert.equal(h.relatives.value[0].relationship_type, 'mother')
  h.service.identity = async () => ({ ...h.details.value, student_id: 92002 })
  await h.reload(); assert.equal(h.details.value, null); assert.match(h.identityError.value, /失败/)
  h.service.identity = async () => ({ student_id: 92001, class_id: 93001, student_no: 'OTHER', student_sequence: '07' })
  await h.reload(); assert.equal(h.details.value, null)
})
test('personal center HTML shows school, class, school number and relation without names or database IDs', async () => {
  const vue = require('vue')
  const { parse, compileScript } = require('@vue/compiler-sfc')
  const { renderToString } = require('@vue/server-renderer')
  const file = fs.readFileSync(path.join(root, 'src/components/student/StudentPersonalCenter.vue'), 'utf8')
  const compiled = compileScript(parse(file).descriptor, { id: 'new-personal-privacy', inlineTemplate: true })
  const component = compile(compiled.content, name => name === 'vue' ? vue : name === '@/student/profile' ? profile : name === '@/student/experience' ? { studentExperience: {} } : {}).default
  const app = vue.createSSRApp(component, {
    account: { username: '私有账号名', full_name: '账号真实姓名', phone: '123-4567' },
    student: student(), binding: binding(),
  })
  const html = await renderToString(app)
  assert.match(html, /所属班级|合成一班/)
  assert.match(html, /SYN-001/)
  assert.match(html, /学生序号待提供/)
  assert.match(html, /父亲/)
  assert.doesNotMatch(html, /不可显示的合成姓名|私有账号名|账号真实姓名|123-4567|92001|93001/)
  assert.doesNotMatch(html, /学习概况|知识点筛选|待订正分类/)
})
