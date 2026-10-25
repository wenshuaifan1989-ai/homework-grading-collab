const assert = require('node:assert/strict')
const { test } = require('node:test')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const vue = require('vue')
const { parse, compileScript } = require('@vue/compiler-sfc')
const { renderToString } = require('@vue/server-renderer')
const root = path.resolve(__dirname, '../src')

function compile(source, resolver) {
  const module = { exports: {} }
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
  } }).outputText, { module, exports: module.exports, Date, Intl, Set, Math, require: resolver })
  return module.exports
}
const helpers = compile(fs.readFileSync(path.join(root, 'student/workbench.ts'), 'utf8'), () => ({}))
const components = new Map()
function loadComponent(relative) {
  const filename = path.resolve(root, relative)
  if (components.has(filename)) return components.get(filename)
  const { descriptor } = parse(fs.readFileSync(filename, 'utf8'))
  const script = compileScript(descriptor, { id: path.basename(filename), inlineTemplate: true })
  const component = compile(script.content, name => name === 'vue' ? vue
    : name === '@/student/workbench' ? helpers
      : name.endsWith('.vue') ? { default: loadComponent(path.relative(root, path.resolve(path.dirname(filename), name))) } : {}).default
  components.set(filename, component)
  return component
}
const navigation = loadComponent('components/student/StudentStudyNavigation.vue')
const workbench = loadComponent('components/student/StudentWorkbench.vue')
async function render(component, props, slots) {
  return renderToString(vue.createSSRApp({ setup: () => () => vue.h(component, props, slots) }))
}

test('assignment toolbar contains horizontal subject choices and no duplicate module links', async () => {
  const html = await render(navigation, {
    page: 'assignments', subjects: ['chinese', 'math'], modelValue: 'math',
    counts: { '': 4, chinese: 1, math: 3 },
  })
  assert.match(html, /作业学科筛选/)
  assert.match(html, /全部学科/)
  assert.match(html, /语文/)
  assert.match(html, /数学/)
  assert.doesNotMatch(html, /<a\b|我的作业|我的错题库|个人中心/)
  const choices = html.match(/<button\b[^>]*>[\s\S]*?<\/button>/g)
  assert.equal(choices.length, 3)
  assert.equal(choices.filter(button => button.includes('aria-pressed="true"')).length, 1)
  assert.match(choices.find(button => button.includes('数学')), /aria-pressed="true"/)
})

test('mistake toolbar keeps exactly one selected subject and offers no mixed-all-subjects choice', async () => {
  const html = await render(navigation, { page: 'mistakes', subjects: ['math', 'english'], modelValue: 'english' })
  assert.match(html, /错题学科筛选/)
  assert.doesNotMatch(html, /全部学科|<a\b/)
  const choices = html.match(/<button\b[^>]*>[\s\S]*?<\/button>/g)
  assert.equal(choices.length, 2)
  assert.equal(choices.filter(button => button.includes('aria-pressed="true"')).length, 1)
  assert.match(choices.find(button => button.includes('英语')), /aria-pressed="true"/)
})

test('profile does not render another module navigation or subject toolbar', async () => {
  const html = await render(navigation, { page: 'profile', subjects: [], modelValue: '' })
  assert.doesNotMatch(html, /<nav\b|<section\b|<a\b|个人中心|学科/)
})

test('workbench places its subject toolbar before content with only a reminder aside', async () => {
  const html = await render(workbench, {}, {
    navigation: () => vue.h('div', 'SUBJECT_FILTER'),
    default: () => vue.h('article', 'ASSIGNMENT_CONTENT'),
    reminders: () => vue.h('p', 'REMINDER_CONTENT'),
  })
  assert.ok(html.indexOf('SUBJECT_FILTER') < html.indexOf('ASSIGNMENT_CONTENT'))
  assert.ok(html.indexOf('ASSIGNMENT_CONTENT') < html.indexOf('REMINDER_CONTENT'))
  assert.equal((html.match(/<aside\b/g) || []).length, 1)
  assert.match(html, /aria-label="学习提醒"/)
  assert.doesNotMatch(html, /aria-label="学生学习导航"/)
})

test('workbench without optional slots has no empty navigation or reminder columns', async () => {
  const html = await render(workbench, {}, { default: () => vue.h('article', 'ONLY_CONTENT') })
  assert.match(html, /ONLY_CONTENT/)
  assert.doesNotMatch(html, /<aside\b|subject-toolbar|with-reminders|学习提醒与待办/)
})
