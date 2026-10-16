<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { learningApi, type AssignmentVariant, type SubjectTierRow } from '@/api/learning'
import { teacherApi, type Assignment, type Classroom } from '@/api/teacher'

type Level = 'L1' | 'L2' | 'L3'
const labels: Record<Level, string> = { L1: '基础巩固', L2: '稳定提升', L3: '拓展挑战' }
const levels: Level[] = ['L1', 'L2', 'L3']
const subjects = [
  { value: 'math', label: '数学' }, { value: 'physics', label: '物理' },
  { value: 'chemistry', label: '化学' }, { value: 'chinese', label: '语文' },
  { value: 'english', label: '英语' }, { value: 'biology', label: '生物' },
]

const classes = ref<Classroom[]>([])
const assignments = ref<Assignment[]>([])
const classId = ref<number | null>(null)
const subject = ref('math')
const assignmentId = ref<number | null>(null)
const tierRows = ref<SubjectTierRow[]>([])
const draftLevels = ref<Record<number, Level | ''>>({})
const selectedStudentIds = ref<number[]>([])
const bulkLevel = ref<Level>('L2')
const historyStudentId = ref<number | null>(null)
const historyItems = ref<Array<{ from_level: string | null; to_level: string; actor_user_id: number; changed_at: string }>>([])
const variants = ref<AssignmentVariant[]>([])
const fallbackEnabled = ref(false)
const fallbackLevel = ref<Level>('L2')
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const notice = ref('')
const variantDrafts = reactive<Record<Level, { questions: string; answers: string }>>({
  L1: { questions: '', answers: '' },
  L2: { questions: '', answers: '' },
  L3: { questions: '', answers: '' },
})

const selectedAssignment = computed(() => assignments.value.find((item) => item.id === assignmentId.value) || null)

function setMessage(message: string) {
  error.value = ''
  notice.value = message
}

function showError(value: any, fallback: string) {
  error.value = value?.response?.data?.detail || value?.response?.data?.message || fallback
  notice.value = ''
}

async function loadTiers() {
  if (!classId.value) return
  loading.value = true
  try {
    const response = await learningApi.listTiers(classId.value, subject.value)
    tierRows.value = response.students
    draftLevels.value = Object.fromEntries(response.students.map((row) => [row.student_id || -row.roster_id, row.level || '']))
    selectedStudentIds.value = []
  } catch (e: any) {
    showError(e, '读取班级学科分层失败。')
  } finally {
    loading.value = false
  }
}

async function loadAssignments() {
  if (!classId.value) {
    assignments.value = []
    assignmentId.value = null
    return
  }
  try {
    assignments.value = await teacherApi.assignments(classId.value)
    if (!assignments.value.some((row) => row.id === assignmentId.value)) {
      assignmentId.value = assignments.value[0]?.id || null
    }
  } catch (e: any) {
    showError(e, '读取班级作业失败。')
  }
}

async function loadVariants() {
  if (!assignmentId.value) return
  try {
    const response = await learningApi.variants(assignmentId.value)
    variants.value = response.variants
    fallbackEnabled.value = response.allow_uniform_fallback
    fallbackLevel.value = response.uniform_fallback_level || 'L2'
    for (const level of ['L1', 'L2', 'L3'] as Level[]) {
      const current = response.variants.find((item) => item.level === level)
      variantDrafts[level].questions = current?.questions.map((item) => item.question_text).join('\n') || ''
      variantDrafts[level].answers = current?.questions.map((item) => item.correct_answer || '').join('\n') || ''
    }
  } catch (e: any) {
    showError(e, '读取分层作业版本失败。')
  }
}

async function saveTier(studentId: number | null, rosterId: number) {
  if (!classId.value || !studentId) {
    error.value = '该名册尚未绑定真实学生身份，不能设置学科层级。'
    return
  }
  const level = draftLevels.value[studentId]
  if (!level) {
    error.value = '请选择层级后再保存。'
    return
  }
  await saveTierEntries([{ student_id: studentId, level }], `已保存 ${tierRows.value.find((row) => row.roster_id === rosterId)?.student_name || '学生'} 的${subjects.find((item) => item.value === subject.value)?.label}分层。`)
}

async function saveBulkTiers() {
  const entries = selectedStudentIds.value.map((studentId) => ({ student_id: studentId, level: bulkLevel.value }))
  if (!entries.length) {
    error.value = '请先勾选至少一名已绑定学生。'
    return
  }
  await saveTierEntries(entries, `已批量更新 ${entries.length} 名学生。`)
}

async function saveTierEntries(entries: Array<{ student_id: number; level: Level }>, successMessage: string) {
  if (!classId.value) return
  saving.value = true
  error.value = ''
  try {
    const result = await learningApi.saveTiers(classId.value, subject.value, entries)
    tierRows.value = result.students
    draftLevels.value = Object.fromEntries(result.students.map((row) => [row.student_id || -row.roster_id, row.level || '']))
    selectedStudentIds.value = []
    setMessage(`${successMessage} 本次新增/变更审计 ${result.changed_count} 条。`)
  } catch (e: any) {
    showError(e, '保存学科分层失败。')
  } finally {
    saving.value = false
  }
}

async function toggleHistory(studentId: number | null) {
  if (!classId.value || !studentId) return
  if (historyStudentId.value === studentId) {
    historyStudentId.value = null
    historyItems.value = []
    return
  }
  try {
    const result = await learningApi.history(classId.value, subject.value, studentId)
    historyStudentId.value = studentId
    historyItems.value = result.items
  } catch (e: any) {
    showError(e, '读取分层历史失败。')
  }
}

function splitLines(value: string) {
  return value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
}

async function saveVariants() {
  if (!assignmentId.value) {
    error.value = '请先选择班级作业。'
    return
  }
  const definitions = (['L1', 'L2', 'L3'] as Level[]).map((level) => {
    const questions = splitLines(variantDrafts[level].questions)
    const answers = variantDrafts[level].answers.split(/\r?\n/)
    return {
      level,
      questions: questions.map((question_text, index) => ({
        question_text,
        correct_answer: answers[index]?.trim() || undefined,
        max_score: 10,
      })),
    }
  })
  const emptyLevel = definitions.find((variant) => !variant.questions.length)
  if (emptyLevel) {
    error.value = `${labels[emptyLevel.level]}还没有题目，三个版本都至少需要一道教师录入题。`
    return
  }
  saving.value = true
  error.value = ''
  try {
    const result = await learningApi.saveVariants(assignmentId.value, {
      allow_uniform_fallback: fallbackEnabled.value,
      uniform_fallback_level: fallbackEnabled.value ? fallbackLevel.value : null,
      variants: definitions,
    })
    variants.value = result.variants
    setMessage('三个版本已保存为新的版本号；学生端只会收到服务端按本人身份匹配的题目内容。')
  } catch (e: any) {
    showError(e, '保存三层作业失败。')
  } finally {
    saving.value = false
  }
}

async function downloadPdf(level: Level) {
  if (!assignmentId.value) return
  try {
    const blob = await learningApi.downloadPdf(assignmentId.value, level)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `assignment-${assignmentId.value}-${level}.pdf`
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (e: any) {
    showError(e, `${labels[level]} PDF 下载失败。`)
  }
}

onMounted(async () => {
  try {
    classes.value = await teacherApi.classes()
    classId.value = classes.value[0]?.id || null
    if (classId.value) {
      await Promise.all([loadTiers(), loadAssignments()])
    }
  } catch (e: any) {
    showError(e, '读取教师班级失败。')
  }
})

watch(subject, async () => {
  historyStudentId.value = null
  if (classId.value) await loadTiers()
})
watch(classId, async () => {
  historyStudentId.value = null
  await Promise.all([loadTiers(), loadAssignments()])
})
watch(assignmentId, () => { void loadVariants() })
</script>

<template>
  <div class="learning-page">
    <header class="page-heading">
      <div><p class="eyebrow">012 · 教师工作台</p><h1>学科分层与分层作业</h1>
        <p class="muted">层级按班级、学生和学科分别维护；作业内容只按服务端身份分配。</p></div>
    </header>

    <div class="learning-toolbar card">
      <label>班级
        <select v-model="classId" :disabled="!classes.length">
          <option v-for="item in classes" :key="item.id" :value="item.id">{{ item.name }}</option>
        </select>
      </label>
      <label>学科
        <select v-model="subject">
          <option v-for="item in subjects" :key="item.value" :value="item.value">{{ item.label }}</option>
        </select>
      </label>
    </div>

    <div v-if="error" class="alert alert-error" role="alert">{{ error }}</div>
    <div v-if="notice" class="alert alert-success" role="status">{{ notice }}</div>

    <section class="card learning-section">
      <div class="section-heading"><div><h2>学生学科分层</h2>
        <p class="muted">未设置时显示“待分层”；提交率和作业成绩不会自动改变层级。</p></div>
      </div>
      <div class="bulk-row">
        <span>已选 {{ selectedStudentIds.length }} 人</span>
        <select v-model="bulkLevel" aria-label="批量设置层级">
          <option v-for="(label, level) in labels" :key="level" :value="level">{{ label }}（{{ level }}）</option>
        </select>
        <button class="btn btn-primary" :disabled="saving || !selectedStudentIds.length" @click="saveBulkTiers">批量保存</button>
      </div>
      <div v-if="!tierRows.length" class="empty-state">当前班级暂无有效名册。</div>
      <div v-else class="table-scroll">
        <table class="learning-table">
          <thead><tr><th>选择</th><th>学生</th><th>学号</th><th>当前层级</th><th>调整</th><th>操作</th></tr></thead>
          <tbody>
            <template v-for="row in tierRows" :key="row.roster_id">
              <tr>
                <td><input v-if="row.student_id" v-model="selectedStudentIds" type="checkbox" :value="row.student_id" :aria-label="`选择${row.student_name}`"></td>
                <td>{{ row.student_name }}</td><td>{{ row.student_no || '—' }}</td>
                <td><span :class="row.level ? 'tier-pill' : 'tier-pill tier-pending'">{{ row.level ? `${row.level_label}（${row.level}）` : '待分层' }}</span></td>
                <td>
                  <select v-if="row.student_id" v-model="draftLevels[row.student_id]" :aria-label="`${row.student_name}的新层级`">
                    <option value="">请选择</option>
                    <option v-for="(label, level) in labels" :key="level" :value="level">{{ label }}（{{ level }}）</option>
                  </select>
                  <span v-else class="muted">先完成学生身份绑定</span>
                </td>
                <td class="actions">
                  <button class="btn btn-secondary btn-sm" :disabled="saving || !row.student_id" @click="saveTier(row.student_id, row.roster_id)">保存</button>
                  <button class="btn btn-ghost btn-sm" :disabled="!row.student_id" @click="toggleHistory(row.student_id)">历史</button>
                </td>
              </tr>
              <tr v-if="historyStudentId === row.student_id" class="history-row"><td colspan="6">
                <strong>{{ row.student_name }} · {{ subject }} 分层历史</strong>
                <span v-if="!historyItems.length" class="muted">暂无变更记录。</span>
                <ul v-else><li v-for="(item, index) in historyItems" :key="index">{{ item.from_level || '未设置' }} → {{ item.to_level }} · {{ item.changed_at }}</li></ul>
              </td></tr>
            </template>
          </tbody>
        </table>
      </div>
    </section>

    <section class="card learning-section">
      <div class="section-heading"><div><h2>三层作业版本</h2>
        <p class="muted">每个 Assignment 保存三个有题面的版本。以下为教师手工录题；正式题目资产需先完成教师确认。</p></div></div>
      <div class="variant-assignment-select">
        <label>班级作业
          <select v-model="assignmentId" :disabled="!assignments.length">
            <option v-for="item in assignments" :key="item.id" :value="item.id">{{ item.title }} · {{ item.assignment_date }}</option>
          </select>
        </label>
        <span v-if="selectedAssignment" class="muted">{{ subjects.find((item) => item.value === selectedAssignment?.subject)?.label || selectedAssignment.subject }} · {{ selectedAssignment.grade }}</span>
      </div>
      <div v-if="!assignments.length" class="empty-state">请先在教师工作台创建并发布班级作业。</div>
      <template v-else>
        <div class="fallback-box">
          <label class="checkbox-label"><input v-model="fallbackEnabled" type="checkbox">允许未分层学生使用教师指定的统一版本</label>
          <label v-if="fallbackEnabled">统一版本
            <select v-model="fallbackLevel"><option v-for="(label, level) in labels" :key="level" :value="level">{{ label }}（{{ level }}）</option></select>
          </label>
          <p class="muted">未启用时，未分层学生不会被静默分配；教师补齐层级或显式开启统一降级后才可提交。</p>
        </div>
        <div class="variant-grid">
          <article v-for="level in levels" :key="level" class="variant-card">
            <div class="variant-title"><h3>{{ labels[level] }}（{{ level }}）</h3>
              <span v-if="variants.find((item) => item.level === level)" class="muted">v{{ variants.find((item) => item.level === level)?.version }}</span></div>
            <label>题目（每行一道）<textarea v-model="variantDrafts[level].questions" rows="5" :placeholder="level === 'L1' ? '如：36 ÷ 6 = ?' : level === 'L2' ? '如：8 × 7 = ?' : '如：若 8x = 56，求 x。'"></textarea></label>
            <label>参考答案（按题目顺序，每行一道；仅教师端）<textarea v-model="variantDrafts[level].answers" rows="3" placeholder="可逐行填写参考答案"></textarea></label>
            <ol class="variant-preview"><li v-for="(question, index) in splitLines(variantDrafts[level].questions)" :key="index">{{ question }}</li></ol>
            <button class="btn btn-secondary btn-sm" :disabled="!variants.some((item) => item.level === level)" @click="downloadPdf(level)">下载可打印 PDF</button>
          </article>
        </div>
        <div class="save-variants-row"><button class="btn btn-primary" :disabled="saving" @click="saveVariants">{{ saving ? '保存中…' : '保存三个版本' }}</button></div>
      </template>
    </section>
  </div>
</template>

<style scoped>
.learning-page { display: grid; gap: 18px; }
.learning-toolbar, .variant-assignment-select, .bulk-row, .section-heading, .variant-title, .save-variants-row { display: flex; align-items: center; gap: 12px; }
.learning-toolbar { flex-wrap: wrap; }
.learning-toolbar label, .variant-assignment-select label { display: grid; gap: 6px; min-width: 220px; font-weight: 600; }
.learning-toolbar select, .learning-table select, .variant-assignment-select select, .fallback-box select { min-height: 38px; padding: 6px 10px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: white; }
.learning-section { padding: 20px; display: grid; gap: 16px; }
.section-heading { justify-content: space-between; }
.section-heading h2 { margin-bottom: 3px; }
.bulk-row { flex-wrap: wrap; padding: 12px; background: var(--color-bg); border-radius: var(--radius); }
.bulk-row span { margin-right: auto; }
.table-scroll { overflow-x: auto; }
.learning-table { width: 100%; border-collapse: collapse; }
.learning-table th, .learning-table td { padding: 10px 12px; border-bottom: 1px solid var(--color-border-light); text-align: left; vertical-align: middle; }
.learning-table th { color: var(--color-text-secondary); font-size: 13px; }
.tier-pill { display: inline-block; padding: 3px 9px; border-radius: 999px; color: #1d4ed8; background: #eff6ff; font-size: 12px; }
.tier-pending { color: #92400e; background: #fffbeb; }
.actions { display: flex; gap: 6px; }
.history-row td { background: #f8fafc; }
.history-row ul { margin: 8px 0 0 20px; }
.variant-assignment-select { flex-wrap: wrap; }
.fallback-box { display: grid; gap: 8px; padding: 14px; border: 1px solid var(--color-border); border-radius: var(--radius); }
.checkbox-label { display: flex; gap: 9px; align-items: center; }
.fallback-box p { margin: 0; }
.variant-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.variant-card { display: grid; align-content: start; gap: 11px; padding: 16px; border: 1px solid var(--color-border); border-radius: var(--radius); }
.variant-title { justify-content: space-between; }
.variant-title h3 { margin: 0; font-size: 16px; }
.variant-card label { display: grid; gap: 6px; font-size: 13px; font-weight: 600; }
.variant-card textarea { width: 100%; padding: 9px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); resize: vertical; font: inherit; font-weight: 400; }
.variant-preview { padding-left: 20px; max-height: 135px; overflow: auto; color: var(--color-text-secondary); font-size: 13px; }
.save-variants-row { justify-content: flex-end; }
@media (max-width: 900px) { .variant-grid { grid-template-columns: 1fr; } }
</style>
