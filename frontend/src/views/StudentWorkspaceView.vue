<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import client from '@/api/client'
import {
  studentApi,
  type LinkedStudent,
  type RosterOption,
  type StudentAssignment,
  type StudentBinding,
} from '@/api/student'
import { homeworkApi, type GradingResultResponse, type TaskStatusResponse } from '@/api/homework'

type DateView = 'today' | 'history' | 'all'

const auth = useAuthStore()
const students = ref<LinkedStudent[]>([])
const assignments = ref<StudentAssignment[]>([])
const selectedStudentId = ref<number | null>(null)
const dateView = ref<DateView>('today')
const binding = ref<StudentBinding | null>(null)
const bindingRequired = ref(false)
const inviteCode = ref('')
const studentName = ref('')
const familyCode = ref('')
const familyRelationship = ref('father')
const familyInviteCode = ref('')
const rosterOptions = ref<RosterOption[]>([])
const selectedRosterId = ref<number | null>(null)
const activeAssignmentId = ref<number | null>(null)
const selectedFiles = ref<File[]>([])
const submissionKey = ref('')
const result = ref<GradingResultResponse | null>(null)
const resultTaskId = ref('')
const retryStatus = ref<TaskStatusResponse | null>(null)
const imageUrls = ref<string[]>([])
const message = ref('')
const error = ref('')
const loading = ref(false)
const submitting = ref(false)
const loadingImages = ref(false)

const isSelfStudent = computed(() => auth.user?.role === 'student')
const today = new Intl.DateTimeFormat('sv-SE', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
}).format(new Date())
const visibleAssignments = computed(() => assignments.value.filter((assignment) => {
  const date = assignment.assignment_date?.slice(0, 10)
  if (dateView.value === 'today') return date === today
  if (dateView.value === 'history') return Boolean(date && date < today)
  return true
}))

function apiError(value: any, fallback: string) {
  return value?.response?.data?.detail || value?.response?.data?.message || fallback
}

async function loadStudents() {
  const { data } = await studentApi.getMyStudents()
  students.value = Array.isArray(data.data) ? data.data : []
  if (!students.value.length) return
  const stillLinked = students.value.some((student) => student.student_id === selectedStudentId.value)
  if (!stillLinked) selectedStudentId.value = students.value[0].student_id
}

async function loadAssignments() {
  if (students.value.length > 1 && !selectedStudentId.value) {
    assignments.value = []
    return
  }
  const studentId = selectedStudentId.value
    || binding.value?.student_id
    || undefined
  const { data } = await studentApi.getAssignments(studentId || undefined)
  assignments.value = Array.isArray(data.data) ? data.data : []
}

async function loadWorkspace() {
  error.value = ''
  loading.value = true
  try {
    if (isSelfStudent.value) {
      try {
        const response = await studentApi.getBinding()
        binding.value = response.data.data
        bindingRequired.value = !response.data.data?.is_bound
      } catch {
        bindingRequired.value = true
      }
    }
    await loadStudents()
    if (isSelfStudent.value && !students.value.length && !binding.value?.is_bound) {
      bindingRequired.value = true
    }
    if (!bindingRequired.value) await loadAssignments()
  } catch (requestError: any) {
    error.value = apiError(requestError, '读取学生作业失败，请稍后重试。')
  } finally {
    loading.value = false
  }
}

async function findRosterOptions() {
  error.value = ''
  message.value = ''
  rosterOptions.value = []
  selectedRosterId.value = null
  if (!inviteCode.value.trim() || !studentName.value.trim()) {
    error.value = '请填写班级邀请码和学生本人姓名。'
    return
  }
  loading.value = true
  try {
    const { data } = await studentApi.getBindingOptions(inviteCode.value.trim(), studentName.value.trim())
    rosterOptions.value = data.data.students || []
    if (rosterOptions.value.length === 1) selectedRosterId.value = rosterOptions.value[0].id
    if (!rosterOptions.value.length) message.value = '没有找到可绑定的同名名册，请核对邀请码和姓名，或联系老师检查名册。'
  } catch (requestError: any) {
    error.value = apiError(requestError, '查询班级名册失败。')
  } finally {
    loading.value = false
  }
}

async function bindStudent() {
  if (!selectedRosterId.value) {
    error.value = '请先查询并选择本人姓名。'
    return
  }
  error.value = ''
  loading.value = true
  try {
    const { data } = await studentApi.bind(inviteCode.value.trim(), studentName.value.trim(), selectedRosterId.value)
    binding.value = data.data
    bindingRequired.value = false
    message.value = `已绑定 ${data.data.class_name || '班级'} · ${data.data.student_name || studentName.value}`
    await auth.refreshIdentity()
    await loadStudents()
    await loadAssignments()
  } catch (requestError: any) {
    error.value = apiError(requestError, '绑定失败，请确认该名册尚未被其他账号绑定。')
  } finally {
    loading.value = false
  }
}

async function claimFamilyBinding() {
  if (!familyCode.value.trim()) {
    error.value = '请填写家庭关系码。'
    return
  }
  error.value = ''
  loading.value = true
  try {
    const { data } = await studentApi.claimFamilyInvite(
      familyCode.value.trim(), familyRelationship.value,
    )
    familyCode.value = ''
    message.value = data.data.already_bound ? '该家庭关系已经存在。' : '家庭关系已建立。'
    await auth.refreshIdentity()
    await loadStudents()
    await loadAssignments()
    bindingRequired.value = !students.value.length
  } catch (requestError: any) {
    error.value = apiError(requestError, '家庭绑定失败，请核对关系码及关系类型。')
  } finally {
    loading.value = false
  }
}

async function createFamilyInvite() {
  if (!selectedStudentId.value) return
  error.value = ''
  try {
    const { data } = await studentApi.createFamilyInvite(selectedStudentId.value)
    familyInviteCode.value = data.data.code
    message.value = '已生成一次性家庭关系码；请只发送给实际家庭成员。'
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(data.data.code).catch(() => undefined)
    }
  } catch (requestError: any) {
    error.value = apiError(requestError, '生成家庭关系码失败。')
  }
}

function openSubmit(assignment: StudentAssignment) {
  if (assignment.variant_mode && !assignment.variant_available) {
    error.value = assignment.variant_message || '老师尚未为当前学生准备好这项作业，请联系老师。'
    return
  }
  activeAssignmentId.value = activeAssignmentId.value === assignment.id ? null : assignment.id
  selectedFiles.value = []
  submissionKey.value = ''
  error.value = ''
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  if (files.length > 9) {
    error.value = '整份作业最多一次选择 9 张图片。'
    selectedFiles.value = []
  } else {
    const supportedTypes = new Set(['image/jpeg', 'image/png', 'image/gif', 'image/bmp'])
    const invalid = files.find((file) => !supportedTypes.has(file.type) || file.size > 10 * 1024 * 1024)
    selectedFiles.value = invalid ? [] : files
    submissionKey.value = ''
    error.value = invalid
      ? (invalid.size > 10 * 1024 * 1024 ? '单张图片不能超过 10MB。' : '仅支持 JPG、PNG、GIF、BMP 图片。')
      : ''
  }
}

async function submitAssignment(assignment: StudentAssignment) {
  error.value = ''
  message.value = ''
  if (!selectedFiles.value.length || selectedFiles.value.length > 9) {
    error.value = '请一次选择 1 至 9 张整份作业图片。'
    return
  }
  submitting.value = true
  try {
    if (!submissionKey.value) {
      const nonce = typeof crypto !== 'undefined' && crypto.randomUUID
        ? crypto.randomUUID()
        : `${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}`
      submissionKey.value = `web_${nonce}`
    }
    const form = new FormData()
    selectedFiles.value.forEach((file) => form.append('files', file, file.name))
    form.append('subject', assignment.subject)
    form.append('grade', assignment.grade)
    form.append('mode', 'vision')
    form.append('assignment_id', String(assignment.id))
    if (assignment.student_id || selectedStudentId.value) {
      form.append('student_id', String(assignment.student_id || selectedStudentId.value))
    }
    const { data } = await studentApi.submitAssignment(form, submissionKey.value)
    message.value = `已一次性提交 ${data.data.image_count || selectedFiles.value.length} 张图片，批改任务已创建。`
    selectedFiles.value = []
    submissionKey.value = ''
    activeAssignmentId.value = null
    await loadAssignments()
  } catch (requestError: any) {
    error.value = apiError(requestError, '提交失败，请检查图片和学生绑定后重试。')
  } finally {
    submitting.value = false
  }
}

function revokeImageUrls() {
  imageUrls.value.forEach((url) => URL.revokeObjectURL(url))
  imageUrls.value = []
}

async function showResult(taskId: string) {
  error.value = ''
  message.value = ''
  result.value = null
  retryStatus.value = null
  resultTaskId.value = taskId
  revokeImageUrls()
  try {
    const statusResponse = await studentApi.getStatus(taskId)
    retryStatus.value = statusResponse.data.data
    const taskStatus = statusResponse.data.data.status
    if (taskStatus !== 'SUCCESS') {
      if (taskStatus === 'WAIT_REVIEW' || taskStatus === 'UNKNOWN_LAYOUT') {
        message.value = taskStatus === 'WAIT_REVIEW'
          ? '本地括号识别结束，等待教师复核。未确认项不算错题，无需重复提交。'
          : '页面未与本次作业完整匹配。请核对试卷后在原作业重新拍照提交，或联系教师检查模板；不会自动调用付费模型。'
        return
      }
      message.value = taskStatus === 'FAILED'
        ? (statusResponse.data.data.failure_message || '本次批改失败，未生成有效成绩。')
        : `作业状态：${statusLabel(taskStatus)}。批改完成后可在此查看结果。`
      return
    }
    const { data } = await studentApi.getResult(taskId)
    result.value = data.data
    if (!data.data.results?.length) {
      result.value = null
      message.value = '批改任务已完成，但没有可显示的题目成绩，请联系老师复核。'
    }
  } catch (requestError: any) {
    try {
      const { data } = await studentApi.getStatus(taskId)
      message.value = `作业状态：${statusLabel(data.data.status)}。批改完成后可在此查看结果。`
    } catch {
      error.value = apiError(requestError, '暂时无法读取批改结果。')
    }
  }
}

async function retryFailedTask() {
  const taskId = retryStatus.value?.task_id
  if (!taskId || !retryStatus.value?.can_retry || submitting.value) return
  const confirmed = window.confirm('上次请求的远端处理/计费状态可能未知。手动重试可能重复计费，系统不会自动重试。仍要继续吗？')
  if (!confirmed) return
  submitting.value = true
  error.value = ''
  try {
    await homeworkApi.retryTask(taskId)
    message.value = '任务已重新排队；如再次超时，请勿连续重复点击。'
    await showResult(taskId)
  } catch (requestError: any) {
    error.value = apiError(requestError, '任务未能重新排队。')
  } finally {
    submitting.value = false
  }
}

async function loadOriginalImages() {
  if (!resultTaskId.value || loadingImages.value) return
  loadingImages.value = true
  revokeImageUrls()
  try {
    for (let index = 0; index < 9; index += 1) {
      try {
        const response = await studentApi.getOriginalImage(resultTaskId.value, index)
        imageUrls.value.push(URL.createObjectURL(response.data))
      } catch (requestError: any) {
        if (requestError.response?.status === 404 && index > 0) break
        throw requestError
      }
    }
    if (!imageUrls.value.length) message.value = '当前任务没有可预览的原始图片。'
  } catch (requestError: any) {
    error.value = apiError(requestError, '读取原始作业图片失败。')
  } finally {
    loadingImages.value = false
  }
}

function statusLabel(status?: string | null) {
  const labels: Record<string, string> = {
    SUCCESS: '已完成', PROCESSING: '处理中', GRADING: '批改中', PENDING: '排队中',
    FAILED: '处理失败', CANCELLED: '已取消',
    WAIT_REVIEW: '答案待教师复核', UNKNOWN_LAYOUT: '页面未匹配，请重拍或联系教师',
  }
  return status ? labels[status] || status : '待提交'
}

function subjectLabel(subject: string) {
  const names: Record<string, string> = {
    math: '数学', chinese: '语文', english: '英语', physics: '物理',
    chemistry: '化学', biology: '生物', history: '历史', geography: '地理',
  }
  return names[subject] || subject
}

onMounted(loadWorkspace)
const originalUrls: string[] = []
async function downloadOriginal(assignment: StudentAssignment) {
  try {
    const response=await client.get(`/teacher-v2/assignments/${assignment.id}/source`,{
      params:{student_id:assignment.student_id||selectedStudentId.value},responseType:'blob'})
    const url=URL.createObjectURL(response.data);originalUrls.push(url)
    const a=document.createElement('a');a.href=url;a.download=`原卷.${assignment.original_format||'pdf'}`;a.click()
  } catch(e:any) {error.value=e.response?.status===404?'原卷不存在或无权查看':'原卷读取失败，请稍后重试'}
}
onBeforeUnmount(()=>{revokeImageUrls();originalUrls.forEach(u=>URL.revokeObjectURL(u))})
</script>

<template>
  <div class="student-workspace">
    <header class="student-page-heading">
      <div><p class="eyebrow">学生工作空间</p><h1>我的作业</h1><p class="muted">查看老师布置的作业，一次提交整份作业图片，并查看批改反馈。</p></div>
      <div v-if="students.length" class="student-picker">
        <label for="student-picker">当前学生</label>
        <select id="student-picker" v-model.number="selectedStudentId" @change="loadAssignments">
          <option v-for="student in students" :key="student.student_id" :value="student.student_id">{{ student.name }}<template v-if="student.relationship_label">（{{ student.relationship_label }}）</template></option>
        </select>
      </div>
    </header>

    <div v-if="error" class="student-alert student-alert-error" role="alert">{{ error }}</div>
    <div v-if="message" class="student-alert student-alert-success" role="status">{{ message }}</div>
    <section v-if="retryStatus?.can_retry" class="student-alert student-alert-error" role="alert">
      <p>{{ retryStatus.failure_message || '本次批改失败，未生成有效成绩。' }}</p>
      <button class="btn btn-secondary btn-sm" :disabled="submitting" @click="retryFailedTask">{{ submitting ? '正在排队…' : '我已了解可能重复计费，手动重试' }}</button>
    </section>

    <section v-if="bindingRequired" class="student-panel student-binding-panel">
      <div class="student-panel-heading"><div><p class="eyebrow">首次使用</p><h2>绑定班级学生身份</h2><p class="muted">输入老师提供的邀请码和学生本人姓名，选择匹配的名册记录。</p></div></div>
      <div class="student-binding-form">
        <label>班级邀请码<input v-model="inviteCode" class="form-input" maxlength="12" autocomplete="off" placeholder="例如：AB12CD34" /></label>
        <label>学生姓名<input v-model="studentName" class="form-input" maxlength="100" autocomplete="name" placeholder="按班级名册填写" /></label>
        <button class="btn btn-primary" :disabled="loading" @click="findRosterOptions">{{ loading ? '查询中…' : '查询名册' }}</button>
      </div>
      <fieldset v-if="rosterOptions.length" class="roster-options">
        <legend>请选择本人名册记录</legend>
        <label v-for="option in rosterOptions" :key="option.id" class="roster-option">
          <input v-model="selectedRosterId" type="radio" :value="option.id" />
          <span>{{ option.student_name }}<small v-if="option.student_no"> · 学号 {{ option.student_no }}</small></span>
        </label>
        <button class="btn btn-primary" :disabled="loading || !selectedRosterId" @click="bindStudent">{{ loading ? '绑定中…' : '确认绑定' }}</button>
      </fieldset>
      <div class="student-binding-form family-binding-form">
        <label>家庭关系码<input v-model="familyCode" class="form-input" maxlength="32" autocomplete="off" placeholder="由已绑定学生的家庭成员提供" /></label>
        <label>与学生的关系<select v-model="familyRelationship" class="form-input"><option value="father">父亲</option><option value="mother">母亲</option><option value="guardian">监护人</option><option value="paternal_grandfather">祖父</option><option value="paternal_grandmother">祖母</option><option value="maternal_grandfather">外祖父</option><option value="maternal_grandmother">外祖母</option><option value="other">其他</option></select></label>
        <button class="btn btn-secondary" :disabled="loading" @click="claimFamilyBinding">{{ loading ? '绑定中…' : '确认家庭绑定' }}</button>
      </div>
    </section>

    <section v-else class="student-panel">
      <div class="student-panel-heading student-assignment-heading">
        <div><p class="eyebrow">班级作业</p><h2>作业列表</h2></div>
        <div class="student-date-tabs" role="tablist" aria-label="作业日期筛选">
          <button :class="{ active: dateView === 'today' }" @click="dateView = 'today'">今日</button>
          <button :class="{ active: dateView === 'history' }" @click="dateView = 'history'">历史</button>
          <button :class="{ active: dateView === 'all' }" @click="dateView = 'all'">全部</button>
        </div>
      </div>
      <div v-if="students.length" class="family-invite-row">
        <button class="btn btn-secondary btn-sm" @click="createFamilyInvite">生成家庭成员邀请</button>
        <code v-if="familyInviteCode">{{ familyInviteCode }}</code>
        <small v-if="familyInviteCode" class="muted">一次性使用；发给实际家庭成员后及时作废/重置。</small>
      </div>
      <p v-if="loading" class="student-empty">正在读取作业…</p>
      <p v-else-if="!visibleAssignments.length" class="student-empty">{{ dateView === 'today' ? '今天暂无作业，切换“历史”查看之前的作业。' : '当前没有可显示的作业。' }}</p>
      <div v-else class="student-assignment-list">
        <article v-for="assignment in visibleAssignments" :key="`${assignment.id}-${assignment.student_id || 'self'}`" class="student-assignment-card">
          <div class="student-assignment-topline"><span class="student-subject">{{ subjectLabel(assignment.subject) }}</span><span>{{ assignment.assignment_date || '未设日期' }}</span></div>
          <h3>{{ assignment.title }}</h3>
          <p class="student-assignment-meta">{{ assignment.class_name }} · {{ assignment.student_name || students.find((item) => item.student_id === selectedStudentId)?.name || '本人' }} · {{ assignment.grade }}</p>
          <p v-if="assignment.description" class="student-assignment-description">{{ assignment.description }}</p>
          <div v-if="assignment.variant_mode" class="student-variant-content">
            <p v-if="!assignment.variant_available" class="student-variant-unavailable">{{ assignment.variant_message || '老师尚未为当前学生准备好这项作业，请联系老师。' }}</p>
            <template v-else>
              <h4>本次练习内容</h4>
              <ol><li v-for="question in assignment.variant_questions" :key="question.id">第{{ question.number }}题 · <strong v-if="question.requirement_label">{{ question.requirement_label }} · </strong>{{ question.question_text }}<small>（{{ question.max_score }} 分）</small></li></ol>
            </template>
          </div>
          <div class="student-assignment-actions">
            <button v-if="assignment.assignment_mode==='uniform_mixed'" class="btn btn-secondary btn-sm" @click="downloadOriginal(assignment)">下载同一原卷</button>
            <span class="student-status" :class="assignment.submitted ? 'is-submitted' : 'is-pending'">{{ assignment.submitted ? statusLabel(assignment.task_status) : '待提交' }}</span>
            <button v-if="assignment.submitted && assignment.task_id" class="btn btn-secondary btn-sm" @click="showResult(assignment.task_id)">查看批改结果</button>
            <button v-if="assignment.submitted && assignment.task_status === 'UNKNOWN_LAYOUT'" class="btn btn-primary btn-sm" @click="openSubmit(assignment)">核对试卷后重新拍照提交</button>
            <button v-if="!assignment.submitted && (!assignment.variant_mode || assignment.variant_available)" class="btn btn-primary btn-sm" @click="openSubmit(assignment)">一次提交整份作业</button>
            <span v-else-if="!assignment.submitted" class="muted">版本未就绪</span>
          </div>
          <div v-if="activeAssignmentId === assignment.id" class="student-upload-box">
            <label class="student-file-picker">选择作业照片<input type="file" accept="image/jpeg,image/png,image/gif,image/bmp" multiple @change="onFileChange" /></label>
            <p class="muted">1–9 张图片会作为同一份作业一次提交；请按页面顺序选全。</p>
            <ul v-if="selectedFiles.length" class="student-file-list"><li v-for="file in selectedFiles" :key="`${file.name}-${file.lastModified}`">{{ file.name }}</li></ul>
            <button class="btn btn-primary" :disabled="submitting || !selectedFiles.length" @click="submitAssignment(assignment)">{{ submitting ? '提交中…' : `提交 ${selectedFiles.length} 张图片` }}</button>
          </div>
        </article>
      </div>
    </section>

    <section v-if="result" class="student-panel student-result-panel">
      <div class="student-panel-heading"><div><p class="eyebrow">批改反馈</p><h2>批改结果</h2></div><button class="btn btn-secondary btn-sm" @click="loadOriginalImages">{{ loadingImages ? '读取中…' : '查看原始作业图片' }}</button></div>
      <div class="student-score-summary"><strong>{{ result.total_score }}<small> / {{ result.total_max_score }}</small></strong><span>正确率 {{ result.total_accuracy == null ? '待统计' : `${Math.round(result.total_accuracy)}%` }}</span></div>
      <div v-if="imageUrls.length" class="student-original-images"><img v-for="(url, index) in imageUrls" :key="url" :src="url" :alt="`第 ${index + 1} 张原始作业图片`" /></div>
      <div v-if="result.results?.length" class="student-question-list">
        <article v-for="item in result.results" :key="item.question_block_id" class="student-question-card">
          <div><strong>第 {{ item.question_no }} 题</strong><span :class="item.result === 'correct' ? 'question-correct' : 'question-review'">{{ item.result === 'correct' ? '正确' : '需订正' }}</span></div>
          <p v-if="item.question_text">{{ item.question_text }}</p>
          <p v-if="item.comment || item.analysis" class="muted">{{ item.comment || item.analysis }}</p>
          <small>得分 {{ item.score }} / {{ item.max_score }}</small>
        </article>
      </div>
    </section>
  </div>
</template>
