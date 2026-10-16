<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { paperApi, type MistakeItem } from '@/api/paper'
import { studentApi, type LinkedStudent } from '@/api/student'

const students = ref<LinkedStudent[]>([])
const selectedStudentId = ref<number | null>(null)
const mistakes = ref<MistakeItem[]>([])
const subjectFilter = ref('')
const knowledgeFilter = ref('')
const dateFilter = ref('')
const drafts = ref<Record<number, string>>({})
const histories = ref<Record<number, Array<Record<string, any>>>>({})
const historyOpen = ref<Record<number, boolean>>({})
const imageUrls = ref<Record<string, string>>({})
const imageKinds = ref<Record<number, 'crop' | 'original'>>({})
const loading = ref(false)
const busyId = ref<number | null>(null)
const error = ref('')
const notice = ref('')

const subjects = computed(() => [...new Set(mistakes.value.map((item) => item.subject).filter(Boolean))] as string[])
const knowledgePoints = computed(() => [...new Set(mistakes.value.flatMap((item) => item.knowledge_points || []))].sort())
const visibleMistakes = computed(() => mistakes.value.filter((item) => {
  if (subjectFilter.value && item.subject !== subjectFilter.value) return false
  if (dateFilter.value && item.created_at?.slice(0, 10) !== dateFilter.value) return false
  const points = item.knowledge_points || []
  if (knowledgeFilter.value === '__unclassified__' && points.length) return false
  if (knowledgeFilter.value && knowledgeFilter.value !== '__unclassified__' && !points.includes(knowledgeFilter.value)) return false
  return true
}))

function apiError(value: any, fallback: string) {
  return value?.response?.data?.detail || value?.response?.data?.message || fallback
}

async function loadStudents() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await studentApi.getMyStudents()
    students.value = (data.data || []).filter((item) => item.status === 'active')
    if (!students.value.some((item) => item.student_id === selectedStudentId.value)) {
      selectedStudentId.value = students.value.length === 1 ? students.value[0].student_id : null
    }
    if (selectedStudentId.value) await loadMistakes()
  } catch (e: any) { error.value = apiError(e, '读取已绑定学生失败。') }
  finally { loading.value = false }
}

async function loadMistakes() {
  if (!selectedStudentId.value) { mistakes.value = []; return }
  loading.value = true
  error.value = ''
  try {
    const response = await paperApi.studentMistakes(selectedStudentId.value)
    mistakes.value = response.items || []
    for (const item of mistakes.value) void loadHistory(item.id)
  } catch (e: any) { error.value = apiError(e, '错题集加载失败。') }
  finally { loading.value = false }
}

function selectStudent(event: Event) {
  selectedStudentId.value = Number((event.target as HTMLSelectElement).value) || null
  void loadMistakes()
}

async function showImage(item: MistakeItem, kind: 'crop' | 'original') {
  imageKinds.value[item.id] = kind
  const key = `${item.id}:${kind}`
  if (imageUrls.value[key]) return
  try {
    const url = kind === 'crop' ? item.crop_url : item.original_url
    const blob = await paperApi.image(url, kind)
    imageUrls.value[key] = URL.createObjectURL(blob)
  } catch (e: any) { error.value = apiError(e, '来源图片暂时无法读取。') }
}

async function loadHistory(mistakeId: number) {
  try { histories.value[mistakeId] = (await paperApi.correctionHistory(mistakeId)).items || [] }
  catch { histories.value[mistakeId] = [] }
}

async function submitCorrection(item: MistakeItem) {
  const answer = (drafts.value[item.id] || '').trim()
  if (!answer) { error.value = '先输入你的订正答案。'; return }
  busyId.value = item.id; error.value = ''; notice.value = ''
  try {
    await paperApi.submitCorrection(item.id, answer)
    drafts.value[item.id] = ''
    notice.value = '订正已提交，教师可在授权班级内查看并反馈。'
    await Promise.all([loadMistakes(), loadHistory(item.id)])
  } catch (e: any) { error.value = apiError(e, '订正提交失败。') }
  finally { busyId.value = null }
}

async function markMastered(item: MistakeItem) {
  busyId.value = item.id; error.value = ''; notice.value = ''
  try {
    await paperApi.markMastered(item.id)
    notice.value = '已记录“自评掌握”；历史记录仍保留。'
    await Promise.all([loadMistakes(), loadHistory(item.id)])
  } catch (e: any) { error.value = apiError(e, '掌握状态保存失败。') }
  finally { busyId.value = null }
}

function toggleHistory(item: MistakeItem) {
  historyOpen.value[item.id] = !historyOpen.value[item.id]
  if (historyOpen.value[item.id] && !histories.value[item.id]) void loadHistory(item.id)
}

onMounted(loadStudents)
onBeforeUnmount(() => Object.values(imageUrls.value).forEach((url) => URL.revokeObjectURL(url)))
</script>

<template>
  <section class="student-paper-page">
    <header class="page-heading"><div><p class="eyebrow">011 · 学生错题集</p><h1>我的错题与订正</h1><p class="muted">只读取当前账号实际绑定学生的错题。原页和单题裁切均可回看。</p></div></header>
    <div v-if="error" class="notice error">{{ error }}</div><div v-if="notice" class="notice success">{{ notice }}</div>
    <section class="filters">
      <label>学生<select :value="selectedStudentId || ''" @change="selectStudent"><option value="">选择已绑定学生</option><option v-for="item in students" :key="item.student_id" :value="item.student_id">{{ item.name }}</option></select></label>
      <label>学科<select v-model="subjectFilter"><option value="">全部学科</option><option v-for="item in subjects" :key="item" :value="item">{{ item }}</option></select></label>
      <label>知识点<select v-model="knowledgeFilter"><option value="">全部知识点</option><option value="__unclassified__">待归类</option><option v-for="item in knowledgePoints" :key="item" :value="item">{{ item }}</option></select></label>
      <label>日期<input v-model="dateFilter" type="date" /></label>
    </section>
    <div v-if="loading && !mistakes.length" class="empty">正在读取错题…</div>
    <div v-else-if="!selectedStudentId" class="empty">请选择一个已绑定学生后查看。</div>
    <div v-else-if="!visibleMistakes.length" class="empty">当前筛选范围暂无错题。</div>
    <article v-for="item in visibleMistakes" :key="item.id" class="mistake-card">
      <div class="card-heading"><div><span class="subject-tag">{{ item.subject || '未标学科' }}</span><span class="question-number">题 {{ item.question_no || '待校对' }}</span><h2>{{ item.question?.question_text || '题面待教师校对' }}</h2></div><span class="status-tag">{{ item.status }}</span></div>
      <div v-if="item.knowledge_points?.length" class="chips"><span v-for="point in item.knowledge_points" :key="point">{{ point }}</span></div><p v-else class="unclassified">待归类知识点</p>
      <div class="answers"><p v-if="item.grading_result">批改得分：{{ item.grading_result.score }} / {{ item.grading_result.max_score }} · {{ item.grading_result.error_type || '错因待分析' }}</p><p v-if="item.question?.correct_answer"><strong>参考答案：</strong>{{ item.question.correct_answer }}</p><p v-if="item.question?.analysis"><strong>解析：</strong>{{ item.question.analysis }}</p></div>
      <div class="image-actions"><button @click="showImage(item, 'crop')">查看单题裁切</button><button @click="showImage(item, 'original')">返回原作业页</button></div>
      <img v-if="imageUrls[`${item.id}:${imageKinds[item.id] || 'crop'}`]" class="evidence-image" :src="imageUrls[`${item.id}:${imageKinds[item.id] || 'crop'}`]" :alt="imageKinds[item.id] === 'original' ? '原始作业页' : '题目裁切图'" />
      <label class="correction-label">我的订正<textarea v-model="drafts[item.id]" rows="3" placeholder="写下重新计算或订正后的答案" /></label>
      <div class="actions"><button class="primary" :disabled="busyId === item.id" @click="submitCorrection(item)">提交订正</button><button class="secondary" :disabled="busyId === item.id" @click="markMastered(item)">标记我已掌握</button><button class="link" @click="toggleHistory(item)">订正历史</button></div>
      <div v-if="historyOpen[item.id]" class="history"><p v-if="!histories[item.id]?.length" class="muted">暂无订正记录</p><div v-for="attempt in histories[item.id] || []" :key="attempt.id" class="history-item"><strong>{{ attempt.attempt_type === 'mark_mastered' ? '自评掌握' : '订正' }} · {{ attempt.status }}</strong><p v-if="attempt.submitted_answer">答案：{{ attempt.submitted_answer }}</p><p v-if="attempt.review_feedback">教师反馈：{{ attempt.review_feedback }}</p><small>{{ attempt.created_at }}</small></div></div>
    </article>
  </section>
</template>

<style scoped>
.student-paper-page{max-width:1000px;margin:0 auto;padding:34px;color:#17243a}.page-heading{margin-bottom:20px}.eyebrow{margin:0 0 8px;color:#2463d3;font-size:12px;font-weight:700;letter-spacing:.08em}.page-heading h1{margin:0;font-size:28px}.muted{color:#738198;font-size:13px}.filters{display:grid;grid-template-columns:1.2fr 1fr 1fr 1fr;gap:12px;background:#fff;border:1px solid #e8edf4;border-radius:14px;padding:16px;margin-bottom:20px}label{display:flex;flex-direction:column;gap:7px;color:#52627a;font-size:13px}select,input,textarea{box-sizing:border-box;width:100%;border:1px solid #dce4ef;border-radius:9px;padding:10px 12px;background:#fff;color:#17243a;font:inherit}.empty{padding:55px;text-align:center;color:#8290a5}.mistake-card{background:#fff;border:1px solid #e8edf4;border-radius:16px;padding:22px;margin:16px 0;box-shadow:0 8px 28px rgba(25,49,82,.05)}.card-heading{display:flex;justify-content:space-between;gap:15px}.card-heading h2{font-size:18px;line-height:1.5;margin:8px 0}.subject-tag,.status-tag,.question-number{display:inline-block;border-radius:999px;padding:5px 10px;font-size:12px;background:#edf4ff;color:#2864d9;margin-right:7px}.status-tag{background:#fff5df;color:#956a15;height:max-content}.chips{display:flex;gap:8px;flex-wrap:wrap}.chips span{border-radius:999px;padding:5px 10px;background:#f0f5f4;color:#347060;font-size:12px}.unclassified{font-size:12px;color:#8a95a6}.answers{line-height:1.65;color:#53627a}.image-actions,.actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:12px 0}.image-actions button,.secondary{border:1px solid #dbe5f2;background:#f7faff;border-radius:8px;padding:9px 13px;color:#2864e8;cursor:pointer}.evidence-image{display:block;width:100%;max-height:440px;object-fit:contain;background:#f5f7fa;border-radius:10px;margin:12px 0}.correction-label{margin:14px 0}.primary{border:0;background:#2864e8;color:#fff;border-radius:8px;padding:10px 15px;cursor:pointer}.link{border:0;background:transparent;color:#2864e8;cursor:pointer}.history{border-top:1px solid #edf0f5;margin-top:15px;padding-top:10px}.history-item{padding:10px 0;border-bottom:1px solid #f0f2f6}.history-item p{margin:6px 0;color:#58677e}.history-item small{color:#8b96a8}.notice{padding:12px 15px;border-radius:10px;margin:12px 0}.notice.error{background:#fff0ef;color:#ae3434}.notice.success{background:#eaf8f0;color:#19744b}@media(max-width:800px){.filters{grid-template-columns:1fr 1fr}}
</style>
