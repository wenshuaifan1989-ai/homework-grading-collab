<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import client from '@/api/client'
import { teacherApi, type Assignment, type CalendarDay, type Classroom, type RosterStudent, type Submission } from '@/api/teacher'

type Tab = 'daily' | 'classes' | 'assignments'
const props = defineProps<{ initialTab?: Tab; classesOnly?: boolean }>()
function localDateString() {
  const today = new Date()
  const pad = (value: number) => String(value).padStart(2, '0')
  return today.getFullYear() + '-' + pad(today.getMonth() + 1) + '-' + pad(today.getDate())
}
const tab = ref<Tab>(props.initialTab || 'daily')
const classes = ref<Classroom[]>([])
const classId = ref<number | null>(null)
const roster = ref<RosterStudent[]>([])
const assignments = ref<Assignment[]>([])
const teachers = ref<Array<{ user_id: number; name: string; role: string }>>([])
const calendarDays = ref<CalendarDay[]>([])
const daily = ref<Record<string, any> | null>(null)
const submissions = ref<Submission[]>([])
const selectedAssignmentId = ref<number | null>(null)
const selectedResult = ref<Record<string, any> | null>(null)
const imagePreviewSrc = ref('')
const imagePreviewError = ref('')
const questionStudents = ref<Record<string, any> | null>(null)
const selectedDate = ref(localDateString())
const loading = ref(false)
const error = ref('')
const notice = ref('')
const newClassName = ref('')
const newClassGrade = ref('')
const newStudentName = ref('')
const newStudentNo = ref('')
const batchLines = ref('')
const teacherInviteCode = ref('')
const teacherJoinCode = ref('')

const selectedClass = computed(() => classes.value.find((item) => item.id === classId.value) || null)
const selectedAssignment = computed(() => assignments.value.find((item) => item.id === selectedAssignmentId.value) || null)
const dateAssignments = computed(() => daily.value?.assignments || [])
const datesInMonth = computed(() => calendarDays.value)

function clearMessages() {
  error.value = ''
  notice.value = ''
}

async function loadClasses() {
  loading.value = true
  try {
    classes.value = await teacherApi.classes()
    if (classes.value.length && !classId.value) classId.value = classes.value[0].id
    if (!classes.value.length) {
      roster.value = []
      assignments.value = []
      teachers.value = []
      daily.value = null
    }
  } catch (e: any) {
    error.value = e.response?.data?.detail || e.response?.data?.message || '班级加载失败'
  } finally {
    loading.value = false
  }
}

async function loadClassData() {
  if (!classId.value) return
  clearMessages()
  loading.value = true
  try {
    const [nextRoster, nextAssignments, nextTeachers] = await Promise.all([
      teacherApi.roster(classId.value),
      teacherApi.assignments(classId.value),
      teacherApi.classTeachers(classId.value),
    ])
    roster.value = nextRoster
    assignments.value = nextAssignments
    teachers.value = nextTeachers
    if (!assignments.value.some((item) => item.id === selectedAssignmentId.value)) {
      selectedAssignmentId.value = null
      submissions.value = []
      selectedResult.value = null
    }
    await loadDaily()
  } catch (e: any) {
    error.value = e.response?.data?.detail || e.response?.data?.message || '班级数据加载失败'
  } finally {
    loading.value = false
  }
}

async function loadDaily() {
  if (!classId.value) return
  try {
    const month = selectedDate.value.slice(0, 7)
    const [calendar, dashboard] = await Promise.all([
      teacherApi.calendar(classId.value, month),
      teacherApi.dailyDashboard(classId.value, selectedDate.value),
    ])
    calendarDays.value = calendar.dates || []
    daily.value = dashboard
  } catch (e: any) {
    daily.value = null
    error.value = e.response?.data?.detail || e.response?.data?.message || '每日教学数据加载失败'
  }
}

watch(classId, (_id, previousId) => {
  if (previousId === null) return
  teacherInviteCode.value = ''
  if (classId.value) {
    void loadClassData()
  } else {
    roster.value = []
    assignments.value = []
    teachers.value = []
    daily.value = null
    calendarDays.value = []
    submissions.value = []
    selectedAssignmentId.value = null
  }
})
watch(selectedDate, () => { void loadDaily() })

onMounted(async () => {
  await loadClasses()
  if (classId.value) await loadClassData()
})
onUnmounted(() => {
  if (imagePreviewSrc.value.startsWith('blob:')) URL.revokeObjectURL(imagePreviewSrc.value)
})

async function createClass() {
  clearMessages()
  if (!newClassName.value.trim()) return
  try {
    const created = await teacherApi.createClass({
      name: newClassName.value.trim(),
      grade: newClassGrade.value || undefined,
    })
    newClassName.value = ''
    newClassGrade.value = ''
    await loadClasses()
    classId.value = created.id
    notice.value = '班级已创建，学生加入码已生成。'
  } catch (e: any) {
    error.value = e.response?.data?.detail || '创建班级失败'
  }
}

async function addStudent() {
  if (!classId.value || !newStudentName.value.trim()) return
  clearMessages()
  try {
    await teacherApi.addStudent(classId.value, {
      student_name: newStudentName.value.trim(),
      student_no: newStudentNo.value.trim() || undefined,
    })
    newStudentName.value = ''
    newStudentNo.value = ''
    await loadClassData()
    notice.value = '学生已加入名册。'
  } catch (e: any) {
    error.value = e.response?.data?.detail || '添加学生失败'
  }
}

async function addBatch() {
  if (!classId.value || !batchLines.value.trim()) return
  clearMessages()
  try {
    await teacherApi.addStudentsBatch(classId.value, batchLines.value)
    batchLines.value = ''
    await loadClassData()
    notice.value = '名册批量导入已完成。'
  } catch (e: any) {
    error.value = e.response?.data?.detail || '批量导入失败，请检查每行“姓名,学号”格式'
  }
}

async function makeTeacherInvite() {
  if (!classId.value) return
  clearMessages()
  try {
    const invite = await teacherApi.createTeacherInvite(classId.value)
    teacherInviteCode.value = invite.code
    notice.value = '教师协作邀请码已生成；请通过受控渠道交给受邀教师。'
  } catch (e: any) {
    error.value = e.response?.data?.detail || '生成教师邀请码失败'
  }
}

async function joinTeacherClass() {
  const code = teacherJoinCode.value.trim()
  clearMessages()
  if (!code) {
    error.value = '请输入教师协作码。'
    return
  }
  try {
    const result = await teacherApi.claimTeacherInvite(code)
    teacherJoinCode.value = ''
    await loadClasses()
    if (classId.value) await loadClassData()
    notice.value = result.already_joined ? '当前账号已是本班协作教师。' : '已通过教师协作码加入班级。'
  } catch (e: any) {
    error.value = e.response?.data?.detail || '教师协作码无效、已使用或已过期。'
  }
}

async function openSubmissions(assignment: Assignment) {
  if (!assignment.id) return
  clearMessages()
  selectedAssignmentId.value = assignment.id
  selectedResult.value = null
  try {
    submissions.value = await teacherApi.submissions(assignment.id)
    tab.value = 'assignments'
  } catch (e: any) {
    error.value = e.response?.data?.detail || '作业提交状态加载失败'
  }
}

async function openStudentResult(row: Submission) {
  if (!selectedAssignmentId.value) return
  if (!row.student_id && !row.student_entity_id) return
  clearMessages()
  try {
    selectedResult.value = row.student_id
      ? await teacherApi.studentResult(selectedAssignmentId.value, row.student_id)
      : await teacherApi.studentEntityResult(selectedAssignmentId.value, row.student_entity_id as number)
    imagePreviewSrc.value = ''
    imagePreviewError.value = ''
  } catch (e: any) {
    error.value = e.response?.data?.detail || '批改结果暂不可用'
  }
}

async function previewOriginalImage(imageIndex: number) {
  if (!selectedResult.value?.task_id) return
  imagePreviewError.value = ''
  if (imagePreviewSrc.value.startsWith('blob:')) URL.revokeObjectURL(imagePreviewSrc.value)
  imagePreviewSrc.value = ''
  try {
    const preview = await teacherApi.originalImagePreview(String(selectedResult.value.task_id), imageIndex)
    if (preview.storage === 'cos' && preview.url) {
      imagePreviewSrc.value = preview.url
      return
    }
    const response = await client.get('/homework/image/' + selectedResult.value.task_id, {
      params: { image_index: imageIndex },
      responseType: 'blob',
    })
    imagePreviewSrc.value = URL.createObjectURL(response.data)
  } catch (e: any) {
    imagePreviewError.value = e.response?.data?.detail || '照片预览暂不可用'
  }
}

async function showQuestionStudents(questionKey: string) {
  const assignmentId = Number(daily.value?.selected_assignment_id)
  if (!assignmentId) {
    error.value = '该日期没有可查看题目明细的已发布作业'
    return
  }
  try {
    questionStudents.value = await teacherApi.questionStudents(assignmentId, questionKey)
  } catch (e: any) {
    error.value = e.response?.data?.detail || '题目学生明细加载失败'
  }
}
</script>

<template>
  <section class="teacher-workspace">
    <header class="workspace-header">
      <div>
        <p class="eyebrow">教师工作台</p>
        <h1>{{ classesOnly ? '班级学生' : '班级每日教学与历史记录' }}</h1>
        <p class="muted">{{ classesOnly ? '班级、名册、身份绑定与教师协作' : '按教学日期查看已有作业、学生提交与成绩；不提供重复发布向导' }}</p>
      </div>
      <label class="class-picker">
        <span>当前班级</span>
        <select v-model.number="classId" class="form-select" aria-label="选择班级">
          <option :value="null">选择班级</option>
          <option v-for="item in classes" :key="item.id" :value="item.id">{{ item.name }}</option>
        </select>
      </label>
    </header>

    <div v-if="error" class="error-message" role="alert">{{ error }}</div>
    <div v-if="notice" class="notice-message" role="status">{{ notice }}</div>

    <nav v-if="!classesOnly" class="workspace-tabs" aria-label="教师工作区">
      <button :class="{ active: tab === 'daily' }" @click="tab = 'daily'">每日教学</button>
      <button :class="{ active: tab === 'assignments' }" @click="tab = 'assignments'">作业与提交</button>
    </nav>

    <div v-if="loading" class="loading-line"><span class="spinner" /> 正在加载…</div>

    <template v-if="tab === 'daily'">
      <section class="card">
        <div class="toolbar">
          <div>
            <h2 class="card-header">每日教学仪表盘</h2>
            <p class="muted">日历仅显示所选班级作业；未绑定学生与未提交状态分开呈现。</p>
          </div>
          <label class="date-field">教学日期
            <input v-model="selectedDate" class="form-input" type="date">
          </label>
        </div>
        <div class="calendar-strip">
          <button
            v-for="day in datesInMonth"
            :key="day.date"
            class="calendar-day"
            :class="{ chosen: day.date === selectedDate }"
            @click="selectedDate = day.date"
          >
            <span>{{ day.date.slice(5) }}</span>
            <small>{{ day.assignment_count }} 项</small>
          </button>
          <p v-if="!datesInMonth.length" class="muted">本月暂无已发布作业。</p>
        </div>
      </section>

      <section v-if="daily" class="stats-grid compact-stats">
        <article class="stat-card"><span class="stat-label">班级名册</span><strong class="stat-value">{{ daily.class?.roster_total ?? 0 }}</strong></article>
        <article class="stat-card"><span class="stat-label">已绑定</span><strong class="stat-value">{{ daily.class?.bound_count ?? 0 }}</strong></article>
        <article class="stat-card"><span class="stat-label">待绑定</span><strong class="stat-value">{{ daily.class?.unbound_count ?? 0 }}</strong></article>
        <article class="stat-card"><span class="stat-label">当日作业</span><strong class="stat-value">{{ dateAssignments.length }}</strong></article>
      </section>

      <section class="card">
        <h2 class="card-header">{{ selectedDate }} 作业</h2>
        <div v-if="dateAssignments.length" class="assignment-grid">
          <button v-for="item in dateAssignments" :key="item.id" class="assignment-tile" @click="openSubmissions(assignments.find((a) => a.id === item.id) || item)">
            <strong>{{ item.title }}</strong>
            <span>{{ item.subject }} · {{ item.grade }}</span>
            <small>已提交 {{ item.submitted_count }} · 未交 {{ item.unsubmitted_count }} · 批改中 {{ item.grading_count }} · 待核对 {{ item.waiting_review_count || 0 }}</small>
          </button>
        </div>
        <div v-else class="empty-state">这一天没有班级作业。</div>
      </section>

      <section v-if="daily" class="panel-grid">
        <article class="card">
          <h2 class="card-header">每题正确 / 错误人数</h2>
          <div class="table-wrapper">
            <table v-if="daily.question_stats?.length" class="data-table">
              <thead><tr><th>题目</th><th>正确</th><th>错误</th><th>待识别</th><th>明细</th></tr></thead>
              <tbody><tr v-for="q in daily.question_stats" :key="q.question_key">
                <td>第 {{ q.question_no }} 题</td><td>{{ q.correct_count }}</td><td>{{ q.wrong_count }}</td><td>{{ q.unrecognized_count }}</td>
                <td><button class="btn btn-secondary btn-sm" @click="showQuestionStudents(q.question_key)">查看</button></td>
              </tr></tbody>
            </table>
            <p v-else class="empty-state">当前日期暂无可统计的批改结果。</p>
          </div>
        </article>
        <article class="card">
          <h2 class="card-header">全班学生状态</h2>
          <div class="table-wrapper">
            <table v-if="daily.students?.length" class="data-table">
              <thead><tr><th>学生</th><th>绑定</th><th>提交/批改状态</th><th>得分</th></tr></thead>
              <tbody><tr v-for="student in daily.students" :key="student.roster_id">
                <td>{{ student.student_name }}<small v-if="student.student_no" class="subline">{{ student.student_no }}</small></td>
                <td>{{ student.bind_status === 'bound' ? '已绑定' : '未绑定' }}</td>
                <td>{{ student.submission_status_label }}</td><td>{{ student.score ?? '—' }}</td>
              </tr></tbody>
            </table>
            <p v-else class="empty-state">暂无学生名册。</p>
          </div>
        </article>
      </section>

      <section v-if="questionStudents" class="card detail-card">
        <div class="toolbar"><h2 class="card-header">第 {{ questionStudents.question_no }} 题学生明细</h2><button class="btn btn-ghost" @click="questionStudents = null">关闭</button></div>
        <div class="panel-grid">
          <div><h3>正确（{{ questionStudents.correct_count }}）</h3><p v-for="s in questionStudents.correct_students" :key="s.roster_id">{{ s.student_name }}</p></div>
          <div><h3>错误（{{ questionStudents.wrong_count }}）</h3><p v-for="s in questionStudents.wrong_students" :key="s.roster_id">{{ s.student_name }}</p></div>
          <div><h3>待识别（{{ questionStudents.unrecognized_count }}）</h3><p v-for="s in questionStudents.unrecognized_students" :key="s.roster_id">{{ s.student_name }}</p></div>
        </div>
      </section>
    </template>

    <template v-else-if="tab === 'classes'">
      <section class="panel-grid">
        <article class="card">
          <h2 class="card-header">加入协作班级</h2>
          <p class="muted">输入班级负责人生成的教师协作码；学生加入码不能用于教师协作。</p>
          <form class="stack" @submit.prevent="joinTeacherClass">
            <label>教师协作码<input v-model="teacherJoinCode" class="form-input" required maxlength="32" autocomplete="off" placeholder="输入教师协作码"></label>
            <button class="btn btn-secondary" :disabled="!teacherJoinCode.trim()">加入协作班级</button>
          </form>
        </article>
        <article class="card">
          <h2 class="card-header">创建班级</h2>
          <form class="stack" @submit.prevent="createClass">
            <label>班级名称<input v-model="newClassName" class="form-input" required maxlength="100" placeholder="如：七年级一班"></label>
            <label>年级（可选）<input v-model="newClassGrade" class="form-input" maxlength="20" placeholder="如：grade7"></label>
            <button class="btn btn-primary" :disabled="!newClassName.trim()">创建班级</button>
          </form>
        </article>
        <article class="card">
          <h2 class="card-header">班级信息与协作</h2>
          <p v-if="selectedClass">班级：<strong>{{ selectedClass.name }}</strong></p>
          <p v-if="selectedClass">学生加入码：<code class="invite-code">{{ selectedClass.invite_code }}</code></p>
          <p class="muted">加入码用于学生选择本人姓名绑定；请只通过受控渠道分享。</p>
          <div class="toolbar">
            <button class="btn btn-secondary" @click="makeTeacherInvite" :disabled="selectedClass?.teacher_role !== 'owner'">生成教师协作码</button>
            <code v-if="teacherInviteCode" class="invite-code">{{ teacherInviteCode }}</code>
          </div>
          <ul class="teacher-list"><li v-for="person in teachers" :key="person.user_id">{{ person.name }} <span class="badge">{{ person.role === 'owner' ? '班级负责人' : '协作教师' }}</span></li></ul>
        </article>
      </section>
      <section class="card">
        <h2 class="card-header">学生名册</h2>
        <form class="form-row" @submit.prevent="addStudent">
          <input v-model="newStudentName" class="form-input" required placeholder="学生姓名">
          <input v-model="newStudentNo" class="form-input" placeholder="学号（可选）">
          <button class="btn btn-primary" :disabled="!classId">添加学生</button>
        </form>
        <details class="batch-import">
          <summary>批量导入名册</summary>
          <p class="muted">每行“姓名,学号”，学号可省略；请勿粘贴无关个人信息。</p>
          <textarea v-model="batchLines" class="form-input" rows="4" placeholder="张同学,2026001&#10;李同学,2026002"></textarea>
          <button class="btn btn-secondary" @click="addBatch" :disabled="!batchLines.trim() || !classId">导入名册</button>
        </details>
        <div class="table-wrapper">
          <table class="data-table"><thead><tr><th>学生</th><th>学号</th><th>绑定状态</th><th>绑定账号</th></tr></thead>
            <tbody><tr v-for="student in roster" :key="student.id">
              <td>{{ student.student_name }}</td><td>{{ student.student_no || '—' }}</td>
              <td>{{ student.bound ? '已绑定' : '待绑定' }}</td><td>{{ student.bound_user_name || '—' }}</td>
            </tr><tr v-if="!roster.length"><td colspan="4" class="empty-cell">尚无名册记录</td></tr></tbody>
          </table>
        </div>
      </section>
    </template>

    <template v-else>
      <section class="panel-grid">
        <article class="card">
          <h2 class="card-header">已发布作业</h2>
          <div v-if="assignments.length" class="assignment-list">
            <button v-for="assignment in assignments" :key="assignment.id" class="assignment-row" @click="openSubmissions(assignment)">
              <span><strong>{{ assignment.title }}</strong><small>{{ assignment.assignment_date }} · {{ assignment.subject }} · {{ assignment.grade }}</small></span>
              <span class="badge">{{ assignment.submission_count || 0 }} 人提交</span>
            </button>
          </div>
          <div v-else class="empty-state">当前班级暂无作业。</div>
        </article>
      </section>
      <section v-if="selectedAssignment" class="card">
        <h2 class="card-header">{{ selectedAssignment.title }}｜提交状态</h2>
        <p class="muted">提交状态来自班级作业接口；得分仅在批改完成后显示，不做排名或百分比。</p>
        <div class="table-wrapper"><table class="data-table">
          <thead><tr><th>学生</th><th>提交</th><th>批改状态</th><th>得分</th><th>结果</th></tr></thead>
          <tbody><tr v-for="student in submissions" :key="student.student_entity_id || student.student_id || student.student_name">
            <td>{{ student.student_name }}</td><td>{{ student.submitted ? '已提交' : '未提交' }}</td><td>{{ student.task_status || '—' }}</td>
            <td>{{ student.total_score ?? '—' }}</td>
            <td><button v-if="student.submitted && student.task_status === 'SUCCESS'" class="btn btn-secondary btn-sm" @click="openStudentResult(student)">查看批改</button><span v-else>—</span></td>
          </tr><tr v-if="!submissions.length"><td colspan="5" class="empty-cell">暂无学生状态</td></tr></tbody>
        </table></div>
      </section>
      <section v-if="selectedResult" class="card">
        <h2 class="card-header">批改结果</h2>
        <p>题目数：{{ selectedResult.total_questions ?? selectedResult.results?.length ?? 0 }}　总分：{{ selectedResult.total_score ?? '—' }}</p>
        <div v-if="selectedResult.images?.length" class="photo-preview">
          <div class="toolbar"><strong>原始作业照片</strong><div class="photo-buttons">
            <button v-for="image in selectedResult.images" :key="image.image_index" class="btn btn-secondary btn-sm" @click="previewOriginalImage(image.image_index)">查看第 {{ image.image_index + 1 }} 页</button>
          </div></div>
          <p v-if="imagePreviewError" class="error-message">{{ imagePreviewError }}</p>
          <img v-if="imagePreviewSrc" :src="imagePreviewSrc" alt="已授权的作业原图预览">
          <p v-if="imagePreviewSrc.startsWith('https://')" class="muted">云端预览链接为短期授权；请勿复制或外传。</p>
        </div>
        <div class="result-list"><article v-for="(result, index) in selectedResult.results || []" :key="index" class="result-row">
          <strong>第 {{ result.question_no }} 题</strong><span>{{ result.score }} / {{ result.max_score }}</span>
          <p>{{ result.comment || result.analysis || '暂无评语' }}</p>
        </article></div>
      </section>
    </template>
  </section>
</template>

<style scoped>
.teacher-workspace { display: grid; gap: 18px; }
.workspace-header, .toolbar, .form-row { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
.workspace-header h1 { margin: 0; font-size: 1.6rem; }
.eyebrow { margin: 0 0 4px; color: #2563eb; font-size: .76rem; font-weight: 700; letter-spacing: .08em; }
.muted { color: #64748b; font-size: .86rem; }
.class-picker { display: grid; gap: 5px; min-width: 190px; color: #64748b; font-size: .8rem; }
.workspace-tabs { display: flex; gap: 8px; overflow-x: auto; border-bottom: 1px solid #dbe3ed; }
.workspace-tabs button { padding: 11px 15px; color: #475569; background: transparent; border-bottom: 2px solid transparent; white-space: nowrap; }
.workspace-tabs button.active { color: #1d4ed8; border-color: #2563eb; font-weight: 700; }
.loading-line { display: flex; gap: 8px; align-items: center; color: #64748b; }
.notice-message { margin: 0; padding: 10px 14px; border: 1px solid #a7f3d0; border-radius: 9px; color: #065f46; background: #ecfdf5; }
.panel-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.compact-stats { margin: 0; }
.compact-stats .stat-card { padding: 15px 18px; }
.compact-stats .stat-value { font-size: 1.45rem; }
.calendar-strip { display: flex; flex-wrap: wrap; gap: 8px; }
.calendar-day { display: grid; gap: 4px; min-width: 72px; padding: 8px 11px; border: 1px solid #dbe3ed; border-radius: 9px; background: white; color: #334155; }
.calendar-day small { color: #64748b; }
.calendar-day.chosen { border-color: #2563eb; color: #1d4ed8; background: #eff6ff; }
.assignment-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 10px; }
.assignment-tile, .assignment-row { display: grid; text-align: left; gap: 7px; padding: 14px; border: 1px solid #dbe3ed; border-radius: 10px; background: #fff; color: #1e293b; }
.assignment-tile span, .assignment-tile small, .assignment-row small { color: #64748b; }
.assignment-row { width: 100%; display: flex; align-items: center; justify-content: space-between; margin: 8px 0; }
.assignment-row > span:first-child { display: grid; gap: 5px; }
.assignment-list { max-height: 370px; overflow: auto; }
.stack { display: grid; gap: 12px; }
.stack label { display: grid; gap: 6px; color: #475569; font-size: .85rem; }
.form-row { align-items: stretch; margin: 12px 0 18px; }
.form-row .form-input { min-width: 0; }
.batch-import { display: grid; gap: 10px; margin: 14px 0; padding: 12px; border: 1px solid #dbe3ed; border-radius: 8px; }
.batch-import summary { cursor: pointer; font-weight: 600; }
.invite-code { display: inline-block; padding: 5px 9px; border-radius: 6px; background: #eff6ff; color: #1d4ed8; font-size: 1rem; letter-spacing: .08em; }
.teacher-list { padding-left: 18px; }
.teacher-list li { margin: 8px 0; }
.data-table { min-width: 580px; }
.data-table .subline { display: block; color: #64748b; font-size: .76rem; }
.empty-cell { padding: 24px; text-align: center; color: #94a3b8; }
.detail-card h3 { margin-top: 0; font-size: .92rem; }
.result-list { display: grid; gap: 8px; }
.result-row { padding: 12px; border: 1px solid #e2e8f0; border-radius: 8px; }
.result-row span { float: right; color: #1d4ed8; font-weight: 700; }
.result-row p { margin-bottom: 0; color: #475569; }
.photo-preview { display: grid; gap: 10px; margin: 16px 0; padding: 14px; border: 1px solid #dbe3ed; border-radius: 9px; }
.photo-buttons { display: flex; flex-wrap: wrap; gap: 8px; }
.photo-preview img { max-width: 100%; max-height: 680px; object-fit: contain; justify-self: start; border: 1px solid #e2e8f0; border-radius: 8px; }
@media (max-width: 720px) {
  .workspace-header, .toolbar { align-items: stretch; flex-direction: column; }
  .panel-grid { grid-template-columns: 1fr; }
  .form-row { flex-direction: column; }
  .workspace-header h1 { font-size: 1.35rem; }
}
</style>
