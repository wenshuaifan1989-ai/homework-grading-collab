<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { paperApi, type MistakeItem, type PaperGradingResult, type PaperSource } from '@/api/paper'
import { teacherApi, type Assignment, type Classroom, type Submission } from '@/api/teacher'
const props = defineProps<{ initialClassId?: number; initialAssignmentId?: number }>()

const classes = ref<Classroom[]>([])
const assignments = ref<Assignment[]>([])
const submissions = ref<Submission[]>([])
const sources = ref<PaperSource[]>([])
const gradingResults = ref<PaperGradingResult[]>([])
const mistakes = ref<MistakeItem[]>([])
const correctionHistories = ref<Record<number, Array<Record<string, any>>>>({})
const historyOpen = ref<Record<number, boolean>>({})
const reviewFeedback = ref<Record<number, string>>({})
const reviewingAttemptId = ref<number | null>(null)
const classId = ref<number | null>(null)
const assignmentId = ref<number | null>(null)
const taskId = ref('')
const studentFilter = ref<number | undefined>()
const selectedSourceId = ref<number | null>(null)
const gradingResultId = ref<number | null>(null)
const questionNo = ref('')
const questionText = ref('')
const questionType = ref('')
const correctAnswer = ref('')
const analysis = ref('')
const x1 = ref(0)
const y1 = ref(0)
const x2 = ref(0)
const y2 = ref(0)
const manualWrong = ref<'auto' | 'yes' | 'no'>('auto')
const cropObjectUrl = ref('')
const originalObjectUrl = ref('')
const showOriginal = ref(false)
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const accuracyStatus = ref('PENDING_REVIEW')

const selectedSource = computed(() => sources.value.find((item) => item.source_id === selectedSourceId.value) || null)
const selectedAssignment = computed(() => assignments.value.find((item) => item.id === assignmentId.value) || null)
const selectedResult = computed(() => gradingResults.value.find((item) => item.id === gradingResultId.value) || null)
const eligibleSubmissions = computed(() => submissions.value.filter((item) => item.task_id && item.task_status === 'SUCCESS'))

function clearMessages() { error.value = ''; notice.value = '' }
function revokeImages() {
  if (cropObjectUrl.value) URL.revokeObjectURL(cropObjectUrl.value)
  if (originalObjectUrl.value) URL.revokeObjectURL(originalObjectUrl.value)
  cropObjectUrl.value = ''
  originalObjectUrl.value = ''
}
function apiError(value: any, fallback: string) {
  return value?.response?.data?.detail || value?.response?.data?.message || fallback
}

async function loadClasses() {
  loading.value = true
  try {
    classes.value = await teacherApi.classes()
    if (!classId.value && classes.value.length) {
      classId.value = props.initialClassId || classes.value[0].id
      await loadAssignments()
      if (props.initialAssignmentId) { assignmentId.value = props.initialAssignmentId; await loadSubmissions() }
    }
  } catch (e: any) { error.value = apiError(e, '班级加载失败。') }
  finally { loading.value = false }
}

async function loadAssignments() {
  clearMessages()
  assignments.value = []
  submissions.value = []
  sources.value = []
  gradingResults.value = []
  taskId.value = ''
  if (!classId.value) return
  try { assignments.value = await teacherApi.assignments(classId.value) }
  catch (e: any) { error.value = apiError(e, '作业加载失败。') }
  await loadClassMistakes()
}

async function loadSubmissions() {
  clearMessages()
  submissions.value = []
  taskId.value = ''
  sources.value = []
  gradingResults.value = []
  if (!assignmentId.value) return
  try { submissions.value = await teacherApi.submissions(assignmentId.value) }
  catch (e: any) { error.value = apiError(e, '学生提交列表加载失败。') }
  await loadClassMistakes()
}

async function loadTaskAssets() {
  if (!taskId.value) return
  clearMessages()
  loading.value = true
  revokeImages()
  try {
    const result = await paperApi.taskAssets(taskId.value)
    sources.value = result.sources || []
    gradingResults.value = result.grading_results || []
    accuracyStatus.value = result.accuracy_status || 'PENDING_REVIEW'
    if (sources.value.length) await selectSource(sources.value[0].source_id)
  } catch (e: any) {
    sources.value = []
    gradingResults.value = []
    error.value = apiError(e, '切题候选加载失败。')
  } finally { loading.value = false }
}

async function digitizeTask() {
  if (!taskId.value) return
  clearMessages()
  busy.value = true
  try {
    const result = await paperApi.digitizeTask(taskId.value)
    sources.value = result.sources || []
    gradingResults.value = (await paperApi.taskAssets(taskId.value)).grading_results || []
    accuracyStatus.value = result.accuracy_status || 'PENDING_REVIEW'
    notice.value = `已生成 ${sources.value.length} 个待校对候选；错题关联须由教师确认。`
    if (sources.value.length) await selectSource(sources.value[0].source_id)
    await loadClassMistakes()
  } catch (e: any) { error.value = apiError(e, '切题候选生成失败，原图仍保留。') }
  finally { busy.value = false }
}

async function selectSource(id: number) {
  selectedSourceId.value = id
  const source = sources.value.find((item) => item.source_id === id)
  if (!source) return
  const result = source.grading_result || gradingResults.value.find((item) => item.question_no === source.question_no)
  gradingResultId.value = result?.id || null
  questionNo.value = source.question_no || result?.question_no || ''
  questionText.value = source.question?.question_text || result?.question_text || ''
  questionType.value = source.question?.question_type || result?.question_type || ''
  correctAnswer.value = source.question?.correct_answer || result?.correct_answer || ''
  analysis.value = source.question?.analysis || result?.analysis || ''
  x1.value = source.bbox.x1; y1.value = source.bbox.y1
  x2.value = source.bbox.x2; y2.value = source.bbox.y2
  showOriginal.value = false
  if (cropObjectUrl.value) URL.revokeObjectURL(cropObjectUrl.value)
  if (originalObjectUrl.value) URL.revokeObjectURL(originalObjectUrl.value)
  cropObjectUrl.value = ''
  originalObjectUrl.value = ''
  try {
    const blob = await paperApi.image(source.crop_url, 'crop')
    cropObjectUrl.value = URL.createObjectURL(blob)
  } catch { error.value = '裁切图暂时无法读取；可返回原作业页面核验。' }
}

function selectGradingResult(event: Event) {
  gradingResultId.value = Number((event.target as HTMLSelectElement).value) || null
  if (!selectedResult.value) return
  questionNo.value = selectedResult.value.question_no || ''
  questionText.value = selectedResult.value.question_text || ''
  questionType.value = selectedResult.value.question_type || ''
  correctAnswer.value = selectedResult.value.correct_answer || ''
  analysis.value = selectedResult.value.analysis || ''
}

async function toggleOriginal() {
  if (!selectedSource.value) return
  showOriginal.value = !showOriginal.value
  if (showOriginal.value && !originalObjectUrl.value) {
    try {
      const blob = await paperApi.image(selectedSource.value.original_url, 'original')
      originalObjectUrl.value = URL.createObjectURL(blob)
    } catch { error.value = '原始作业页暂时无法读取。' }
  }
}

async function saveReview() {
  if (!selectedSource.value || !gradingResultId.value) {
    error.value = '请先选择该候选对应的批改题目。'
    return
  }
  clearMessages()
  busy.value = true
  try {
    const result = await paperApi.reviewSource(selectedSource.value.source_id, {
      grading_result_id: gradingResultId.value,
      question_no: questionNo.value.trim() || undefined,
      question_text: questionText.value,
      question_type: questionType.value || undefined,
      correct_answer: correctAnswer.value || undefined,
      analysis: analysis.value || undefined,
      x1: x1.value, y1: y1.value, x2: x2.value, y2: y2.value,
      manual_wrong: manualWrong.value === 'auto' ? null : manualWrong.value === 'yes',
      confirm: true,
    })
    notice.value = result.mistake_created
      ? '题目已确认并进入该学生错题集。'
      : (result.mistake_status_reason || '题目与来源已确认；清洁视觉版仍待人工复核。')
    await loadTaskAssets()
    await loadClassMistakes()
  } catch (e: any) { error.value = apiError(e, '题目校对未保存。') }
  finally { busy.value = false }
}

async function loadClassMistakes() {
  if (!classId.value) return
  try {
    const response = await paperApi.classMistakes(classId.value, studentFilter.value)
    mistakes.value = response.items || []
  } catch { mistakes.value = [] }
}

async function toggleCorrectionHistory(item: MistakeItem) {
  historyOpen.value[item.id] = !historyOpen.value[item.id]
  if (historyOpen.value[item.id] && !correctionHistories.value[item.id]) {
    try {
      correctionHistories.value[item.id] = (await paperApi.correctionHistory(item.id)).items || []
    } catch (e: any) {
      error.value = apiError(e, '订正记录读取失败。')
      correctionHistories.value[item.id] = []
    }
  }
}

async function reviewCorrection(item: MistakeItem, attempt: Record<string, any>, accepted: boolean) {
  reviewingAttemptId.value = Number(attempt.id)
  clearMessages()
  try {
    await paperApi.reviewCorrection(
      item.id,
      Number(attempt.id),
      accepted,
      reviewFeedback.value[item.id]?.trim() || undefined,
    )
    notice.value = accepted ? '订正已通过，错题状态已更新。' : '已退回订正并要求学生重做。'
    correctionHistories.value[item.id] = (await paperApi.correctionHistory(item.id)).items || []
    await loadClassMistakes()
  } catch (e: any) { error.value = apiError(e, '教师复核失败。') }
  finally { reviewingAttemptId.value = null }
}

async function onStudentFilter() { await loadClassMistakes() }

async function openMistakeSource(item: MistakeItem) {
  if (!item.source_id) { error.value = '该错题没有可回溯的题目来源。'; return }
  clearMessages()
  loading.value = true
  taskId.value = item.source_task_id
  try {
    const result = await paperApi.taskAssets(item.source_task_id)
    sources.value = result.sources || []
    gradingResults.value = result.grading_results || []
    accuracyStatus.value = result.accuracy_status || 'PENDING_REVIEW'
    await selectSource(item.source_id)
    document.querySelector('.review-layout')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  } catch (e: any) { error.value = apiError(e, '题目来源读取失败。') }
  finally { loading.value = false }
}

onMounted(loadClasses)
onBeforeUnmount(revokeImages)
</script>

<template>
  <section class="paper-page">
    <header class="page-heading">
      <div><p class="eyebrow">作业详情</p><h1>本作业错题与订正审核</h1>
        <p class="muted">只处理已批改完成的班级作业；题号、题面和裁切边界由教师确认后才形成错题关系。</p></div>
      <span class="pending-pill">准确率：{{ accuracyStatus }}</span>
    </header>

    <div v-if="error" class="notice error">{{ error }}</div>
    <div v-if="notice" class="notice success">{{ notice }}</div>

    <section class="paper-card controls">
      <label>班级<select v-model.number="classId" @change="loadAssignments"><option :value="null">选择班级</option><option v-for="item in classes" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
      <label>作业<select v-model.number="assignmentId" @change="loadSubmissions"><option :value="null">选择作业</option><option v-for="item in assignments" :key="item.id" :value="item.id">{{ item.title }} · {{ item.assignment_date }}</option></select></label>
      <label>已批改提交<select v-model="taskId" @change="loadTaskAssets"><option value="">选择学生作业</option><option v-for="item in eligibleSubmissions" :key="item.task_id || String(item.student_entity_id || item.student_id || 'unknown')" :value="item.task_id">{{ item.student_name }} · {{ item.task_id }}</option></select></label>
      <button class="primary" :disabled="!taskId || busy" @click="digitizeTask">{{ busy ? '处理中…' : '生成 / 重用切题候选' }}</button>
    </section>

    <section v-if="taskId" class="review-layout">
      <div class="paper-card candidate-panel">
        <div class="section-heading"><div><h2>逐题候选</h2><p class="muted">每题保留页序、边界框、裁切图和原始证据。</p></div><span class="count-pill">{{ sources.length }}</span></div>
        <div v-if="loading" class="empty-state">正在读取候选…</div>
        <div v-else-if="!sources.length" class="empty-state">尚无切题候选。点击上方按钮生成；切题失败时原图仍保留。</div>
        <button v-for="item in sources" :key="item.source_id" class="source-row" :class="{ active: selectedSourceId === item.source_id }" @click="selectSource(item.source_id)">
          <span class="source-index">{{ item.question_no || `候选 ${item.source_id}` }}</span>
          <span class="source-meta">第 {{ item.page_index + 1 }} 页 · {{ item.review_status }} · {{ item.provider }}</span>
          <span class="source-meta">框 {{ item.bbox.x1 }},{{ item.bbox.y1 }}–{{ item.bbox.x2 }},{{ item.bbox.y2 }}</span>
        </button>
      </div>

      <div v-if="selectedSource" class="paper-card editor-panel">
        <div class="section-heading"><div><h2>确认题目与来源</h2><p class="muted">清洁图未高置信复原，状态保留 PENDING_REVIEW。</p></div><button class="text-button" @click="toggleOriginal">{{ showOriginal ? '查看裁切图' : '查看原作业页' }}</button></div>
        <img v-if="showOriginal && originalObjectUrl" class="evidence-image original" :src="originalObjectUrl" alt="原始作业页证据" />
        <img v-else-if="cropObjectUrl" class="evidence-image" :src="cropObjectUrl" alt="单题裁切候选" />
        <p class="muted image-caption">{{ showOriginal ? '原始页只读留存，不被裁切覆盖。' : `来源页 ${selectedSource.page_index + 1} 的裁切视觉版` }}</p>
        <label>关联批改题<select :value="gradingResultId || ''" @change="selectGradingResult"><option value="">请选择批改结果</option><option v-for="item in gradingResults" :key="item.id" :value="item.id">题号 {{ item.question_no }} · {{ item.result }} · 置信度 {{ item.confidence ?? '未知' }}</option></select></label>
        <div class="field-grid"><label>题号<input v-model="questionNo" maxlength="40" /></label><label>题型<input v-model="questionType" maxlength="80" /></label></div>
        <label>题面（教师校对）<textarea v-model="questionText" rows="4" placeholder="题面未识别时请按裁切图校对；不要补造信息" /></label>
        <div class="field-grid"><label>x1<input v-model.number="x1" type="number" min="0" /></label><label>y1<input v-model.number="y1" type="number" min="0" /></label><label>x2<input v-model.number="x2" type="number" min="1" /></label><label>y2<input v-model.number="y2" type="number" min="1" /></label></div>
        <label>可信答案（可空）<textarea v-model="correctAnswer" rows="2" placeholder="没有可信答案时留空" /></label>
        <label>解析（可空）<textarea v-model="analysis" rows="3" placeholder="仅保留可信解析" /></label>
        <label>错题判定<select v-model="manualWrong"><option value="auto">按高置信模型判错；低/未知置信不自动入集</option><option value="yes">教师确认是错题</option><option value="no">教师确认不是错题</option></select></label>
        <button class="primary" :disabled="busy || !gradingResultId" @click="saveReview">确认题目并保存</button>
      </div>
    </section>

    <section class="paper-card mistake-panel">
      <div class="section-heading"><div><h2>本人授权班级错题</h2><p class="muted">按当前教师的班级权限过滤，不开放平台管理员批量查看入口。</p></div>
        <select v-model.number="studentFilter" @change="onStudentFilter"><option :value="undefined">全班</option><option v-for="item in submissions" :key="String(item.student_entity_id || item.student_id || item.student_name)" :value="item.student_entity_id || item.student_id">{{ item.student_name }}</option></select>
      </div>
      <div v-if="!mistakes.length" class="empty-state">当前筛选范围暂无已确认错题。</div>
      <article v-for="item in mistakes" :key="item.id" class="mistake-row">
        <div class="mistake-detail"><strong>{{ item.student_name }} · {{ item.question_no || '待标题号' }}</strong><p>{{ item.question?.question_text || '题面待校对' }}</p><small>{{ item.assignment_title }} · {{ item.subject }} · {{ item.status }}</small>
          <button class="text-button" @click="toggleCorrectionHistory(item)">{{ historyOpen[item.id] ? '收起订正记录' : '查看订正记录' }}</button>
          <button class="text-button" @click="openMistakeSource(item)">打开对应题源进行校对</button>
          <div v-if="historyOpen[item.id]" class="correction-history">
            <p v-if="!correctionHistories[item.id]?.length" class="muted">暂无订正记录</p>
            <article v-for="attempt in correctionHistories[item.id] || []" :key="attempt.id" class="attempt-row">
              <strong>{{ attempt.attempt_type === 'mark_mastered' ? '学生自评掌握' : '学生订正' }} · {{ attempt.status }}</strong>
              <p v-if="attempt.submitted_answer">答案：{{ attempt.submitted_answer }}</p>
              <p v-if="attempt.review_feedback">教师反馈：{{ attempt.review_feedback }}</p>
              <small>{{ attempt.created_at }}</small>
              <template v-if="attempt.attempt_type === 'correction' && attempt.status === 'submitted'">
                <label>反馈（可选）<textarea v-model="reviewFeedback[item.id]" rows="2" placeholder="通过或退回时给学生的说明" /></label>
                <div class="review-actions"><button class="primary" :disabled="reviewingAttemptId === attempt.id" @click="reviewCorrection(item, attempt, true)">通过订正</button><button class="secondary" :disabled="reviewingAttemptId === attempt.id" @click="reviewCorrection(item, attempt, false)">退回重做</button></div>
              </template>
            </article>
          </div>
        </div>
        <span class="basis">{{ item.detection_basis }}</span>
      </article>
    </section>
  </section>
</template>

<style scoped>
.paper-page{max-width:1180px;margin:0 auto;padding:34px;color:#17243a}.page-heading,.section-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:18px}.page-heading{margin-bottom:24px}.eyebrow{margin:0 0 8px;color:#2463d3;font-size:12px;font-weight:700;letter-spacing:.08em}.page-heading h1{margin:0;font-size:28px}.muted{color:#738198;font-size:13px;line-height:1.55}.pending-pill,.count-pill,.basis{align-self:center;border-radius:999px;background:#fff5df;color:#92620a;padding:7px 12px;font-size:12px;white-space:nowrap}.paper-card{border:1px solid #e8edf4;border-radius:16px;background:#fff;box-shadow:0 8px 28px rgba(25,49,82,.05);padding:22px;margin-bottom:20px}.controls{display:grid;grid-template-columns:1fr 1fr 1.4fr auto;align-items:end;gap:14px}label{display:flex;flex-direction:column;gap:7px;color:#52627a;font-size:13px}input,select,textarea{box-sizing:border-box;width:100%;border:1px solid #dce4ef;border-radius:9px;padding:10px 12px;background:#fff;color:#17243a;font:inherit}textarea{resize:vertical}.primary{border:0;border-radius:9px;padding:11px 16px;background:#2864e8;color:#fff;font-weight:650;cursor:pointer}.primary:disabled{opacity:.55;cursor:not-allowed}.review-layout{display:grid;grid-template-columns:minmax(260px,.8fr) minmax(420px,1.5fr);gap:20px;align-items:start}.section-heading{align-items:center;margin-bottom:16px}.section-heading h2{margin:0;font-size:18px}.section-heading p{margin:5px 0 0}.source-row{display:block;width:100%;text-align:left;border:1px solid #e8edf4;border-radius:10px;background:#fff;padding:12px 14px;margin-top:9px;cursor:pointer;color:#17243a}.source-row.active{border-color:#3a73ea;background:#f5f8ff}.source-index{display:block;font-weight:700}.source-meta{display:block;margin-top:5px;color:#748198;font-size:12px}.editor-panel>label{margin-top:14px}.field-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:14px}.field-grid:first-of-type{grid-template-columns:1fr 1fr}.evidence-image{display:block;width:100%;max-height:300px;object-fit:contain;background:#f5f7fa;border-radius:10px}.evidence-image.original{max-height:430px}.image-caption{margin:7px 0 12px}.text-button{border:0;background:none;color:#2864e8;cursor:pointer}.empty-state{padding:24px 12px;text-align:center;color:#8491a5;font-size:13px}.mistake-row{display:flex;justify-content:space-between;gap:18px;padding:14px 0;border-top:1px solid #eef1f6}.mistake-row p{margin:7px 0}.mistake-row small{color:#77849a}.mistake-detail{flex:1;min-width:0}.correction-history{margin-top:12px;padding:12px;border-radius:10px;background:#f8faff}.attempt-row{padding:12px 0;border-bottom:1px solid #e7edf6}.attempt-row p{margin:7px 0}.attempt-row small{color:#7c8798}.attempt-row label{margin-top:10px}.review-actions{display:flex;gap:10px;margin-top:10px}.secondary{border:1px solid #dbe5f2;background:#f7faff;border-radius:8px;padding:9px 13px;color:#2864e8;cursor:pointer}.notice{padding:12px 15px;border-radius:10px;margin:12px 0}.notice.error{background:#fff0ef;color:#ae3434}.notice.success{background:#eaf8f0;color:#19744b}@media(max-width:850px){.controls{grid-template-columns:1fr 1fr}.review-layout{grid-template-columns:1fr}.field-grid{grid-template-columns:repeat(2,1fr)}}
</style>
