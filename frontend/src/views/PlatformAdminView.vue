<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { platformAdminApi } from '@/api/platformAdmin'

type Section = 'users' | 'teachers' | 'students' | 'schools' | 'classes' | 'bindings' | 'homework'
const sections: Array<{ id: Section; label: string }> = [
  { id: 'users', label: '账号' },
  { id: 'teachers', label: '教师' },
  { id: 'students', label: '学生' },
  { id: 'schools', label: '学校' },
  { id: 'classes', label: '班级与名册' },
  { id: 'bindings', label: '家庭绑定' },
  { id: 'homework', label: '作业归属' },
]
const section = ref<Section>('users')
const query = ref('')
const rows = ref<any[]>([])
const classes = ref<any[]>([])
const selectedClassId = ref<number | null>(null)
const classRoster = ref<any[]>([])
const loading = ref(false)
const error = ref('')
const notice = ref('')
const editBinding = ref<any | null>(null)
const editRoster = ref<any | null>(null)
const teacherForm = ref({ full_name: '', phone: '', password: '' })
let searchTimer: ReturnType<typeof setTimeout> | null = null

const selectedClass = computed(() => classes.value.find((row) => row.id === selectedClassId.value) || null)

async function loadSection() {
  loading.value = true
  error.value = ''
  notice.value = ''
  try {
    if (section.value === 'users') rows.value = await platformAdminApi.users(query.value)
    else if (section.value === 'teachers') rows.value = await platformAdminApi.teachers(query.value)
    else if (section.value === 'students') rows.value = await platformAdminApi.students(query.value)
    else if (section.value === 'schools') rows.value = await platformAdminApi.schools(query.value)
    else if (section.value === 'bindings') {
      const values = await platformAdminApi.bindings()
      rows.value = query.value.trim()
        ? values.filter((row) => JSON.stringify(row).toLowerCase().includes(query.value.trim().toLowerCase()))
        : values
    }
    else if (section.value === 'homework') {
      const values = await platformAdminApi.homework()
      rows.value = query.value.trim()
        ? values.filter((row) => JSON.stringify(row).toLowerCase().includes(query.value.trim().toLowerCase()))
        : values
    }
    else {
      classes.value = await platformAdminApi.classes()
      if (!selectedClassId.value && classes.value.length) selectedClassId.value = classes.value[0].id
      rows.value = classes.value
      if (selectedClassId.value) classRoster.value = await platformAdminApi.classRoster(selectedClassId.value)
    }
  } catch (e: any) {
    error.value = e.response?.data?.detail || e.response?.data?.message || '管理数据加载失败'
    rows.value = []
  } finally {
    loading.value = false
  }
}

watch(section, () => { void loadSection() })
watch(query, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { void loadSection() }, 250)
})
watch(selectedClassId, async (id) => {
  if (section.value !== 'classes' || !id) return
  try {
    classRoster.value = await platformAdminApi.classRoster(id)
  } catch (e: any) {
    error.value = e.response?.data?.detail || '名册读取失败'
  }
})
onMounted(() => { void loadSection() })
onUnmounted(() => { if (searchTimer) clearTimeout(searchTimer) })

async function toggleUser(row: any) {
  error.value = ''
  try {
    await platformAdminApi.setUserStatus(row.id, !row.is_active)
    await loadSection()
    notice.value = '账号状态已更新。'
  } catch (e: any) {
    error.value = e.response?.data?.detail || '账号状态更新失败'
  }
}

async function toggleTeacher(row: any) {
  error.value = ''
  try {
    await platformAdminApi.setTeacherStatus(row.id, !row.is_active)
    await loadSection()
    notice.value = '教师账号状态已更新。'
  } catch (e: any) {
    error.value = e.response?.data?.detail || '教师状态更新失败'
  }
}

async function createTeacher() {
  error.value = ''
  try {
    await platformAdminApi.createTeacher(teacherForm.value)
    teacherForm.value = { full_name: '', phone: '', password: '' }
    await loadSection()
    notice.value = '教师账号已创建。请使用受控渠道交付初始密码。'
  } catch (e: any) {
    error.value = e.response?.data?.detail || '创建教师失败'
  }
}

function beginBindingEdit(row: any) {
  editBinding.value = {
    ...row,
    relationship_type: row.relationship_type || 'guardian',
    relationship_label: row.relationship_label || '',
    status: row.status || 'active',
  }
}

async function saveBinding() {
  if (!editBinding.value) return
  error.value = ''
  try {
    await platformAdminApi.correctFamilyBinding(editBinding.value.student_id, {
      user_id: editBinding.value.user_id,
      relationship_type: editBinding.value.relationship_type,
      relationship_label: editBinding.value.relationship_label || null,
      status: editBinding.value.status,
    })
    editBinding.value = null
    await loadSection()
    notice.value = '家庭绑定关系已更新。'
  } catch (e: any) {
    error.value = e.response?.data?.detail || '家庭绑定纠错失败'
  }
}

function beginRosterEdit(row: any) {
  editRoster.value = { ...row, student_id_text: row.student_id == null ? '' : String(row.student_id) }
}

async function saveRosterLink() {
  if (!selectedClassId.value || !editRoster.value) return
  const input = editRoster.value.student_id_text.trim()
  const studentId = input ? Number(input) : null
  if (input && (!Number.isInteger(studentId) || (studentId as number) <= 0)) {
    error.value = '学生档案 ID 必须是正整数，留空表示解除关联'
    return
  }
  error.value = ''
  try {
    await platformAdminApi.correctRosterStudent(selectedClassId.value, editRoster.value.id, studentId)
    editRoster.value = null
    await loadSection()
    notice.value = '名册学生关联已更新。'
  } catch (e: any) {
    error.value = e.response?.data?.detail || '名册关联纠错失败'
  }
}
</script>

<template>
  <section class="platform-admin">
    <header class="admin-heading">
      <div><p class="eyebrow">独立管理入口</p><h1>平台管理</h1><p class="muted">使用现有 platform_admin API；服务端继续执行全部权限校验。</p></div>
      <button class="btn btn-secondary" @click="loadSection">刷新</button>
    </header>
    <div v-if="error" class="error-message" role="alert">{{ error }}</div>
    <div v-if="notice" class="notice-message" role="status">{{ notice }}</div>
    <nav class="admin-tabs" aria-label="平台管理模块">
      <button v-for="item in sections" :key="item.id" :class="{ active: section === item.id }" @click="section = item.id">{{ item.label }}</button>
    </nav>
    <div class="admin-toolbar">
      <label v-if="!['classes'].includes(section)" class="search-box">搜索
        <input v-model="query" class="form-input" :placeholder="'搜索' + sections.find((item) => item.id === section)?.label">
      </label>
      <span v-if="loading" class="muted"><span class="spinner" /> 加载中</span>
    </div>

    <section v-if="section === 'users'" class="card">
      <h2 class="card-header">账号与状态</h2>
      <div class="table-wrapper"><table class="data-table"><thead><tr><th>ID</th><th>姓名/账号</th><th>手机号</th><th>角色</th><th>状态</th><th>操作</th></tr></thead>
        <tbody><tr v-for="row in rows" :key="row.id"><td>{{ row.id }}</td><td>{{ row.full_name || row.username }}</td><td>{{ row.phone || '—' }}</td><td>{{ row.roles?.join(' / ') || row.role }}</td><td>{{ row.is_active ? '启用' : '停用' }}</td><td><button class="btn btn-secondary btn-sm" @click="toggleUser(row)">{{ row.is_active ? '停用' : '启用' }}</button></td></tr>
          <tr v-if="!rows.length"><td colspan="6" class="empty-cell">没有匹配账号</td></tr></tbody>
      </table></div>
    </section>

    <template v-else-if="section === 'teachers'">
      <section class="card">
        <h2 class="card-header">创建教师账号</h2>
        <form class="teacher-create" @submit.prevent="createTeacher">
          <input v-model="teacherForm.full_name" class="form-input" required placeholder="教师姓名">
          <input v-model="teacherForm.phone" class="form-input" required inputmode="tel" placeholder="手机号">
          <input v-model="teacherForm.password" class="form-input" required minlength="8" type="password" autocomplete="new-password" placeholder="初始密码（至少8位）">
          <button class="btn btn-primary">创建教师</button>
        </form>
        <p class="muted">初始密码仅提交给现有受权限保护的 API，不展示在列表或反馈中。</p>
      </section>
      <section class="card">
        <h2 class="card-header">教师账号</h2>
        <div class="table-wrapper"><table class="data-table"><thead><tr><th>ID</th><th>姓名</th><th>手机号</th><th>班级数</th><th>状态</th><th>操作</th></tr></thead>
          <tbody><tr v-for="row in rows" :key="row.id"><td>{{ row.id }}</td><td>{{ row.full_name || '—' }}</td><td>{{ row.phone }}</td><td>{{ row.class_count }}</td><td>{{ row.is_active ? '启用' : '停用' }}</td><td><button class="btn btn-secondary btn-sm" @click="toggleTeacher(row)">{{ row.is_active ? '停用' : '启用' }}</button></td></tr>
            <tr v-if="!rows.length"><td colspan="6" class="empty-cell">没有匹配教师</td></tr></tbody>
        </table></div>
      </section>
    </template>

    <section v-else-if="section === 'students'" class="card">
      <h2 class="card-header">学生档案概览</h2>
      <div class="table-wrapper"><table class="data-table"><thead><tr><th>ID</th><th>姓名</th><th>状态</th><th>名册关联数</th></tr></thead>
        <tbody><tr v-for="row in rows" :key="row.id"><td>{{ row.id }}</td><td>{{ row.name }}</td><td>{{ row.status }}</td><td>{{ row.roster_count }}</td></tr><tr v-if="!rows.length"><td colspan="4" class="empty-cell">没有匹配学生</td></tr></tbody>
      </table></div>
    </section>

    <section v-else-if="section === 'schools'" class="card">
      <h2 class="card-header">学校目录</h2>
      <div class="table-wrapper"><table class="data-table"><thead><tr><th>ID</th><th>学校</th><th>省 / 市 / 区</th><th>学段</th><th>状态</th><th>来源</th></tr></thead>
        <tbody><tr v-for="row in rows" :key="row.id"><td>{{ row.id }}</td><td>{{ row.official_name }}</td><td>{{ [row.province, row.city, row.district].filter(Boolean).join(' / ') || '—' }}</td><td>{{ row.stage || '—' }}</td><td>{{ row.status }}</td><td>{{ row.is_custom ? '自定义待规范' : '目录' }}</td></tr><tr v-if="!rows.length"><td colspan="6" class="empty-cell">没有匹配学校</td></tr></tbody>
      </table></div>
    </section>

    <section v-else-if="section === 'classes'" class="card">
      <h2 class="card-header">班级与学生名册</h2>
      <label class="search-box">选择班级
        <select v-model.number="selectedClassId" class="form-select"><option v-for="row in classes" :key="row.id" :value="row.id">{{ row.name }}（ID {{ row.id }}）</option></select>
      </label>
      <p v-if="selectedClass" class="muted">负责教师：{{ selectedClass.teacher_name || selectedClass.teacher_id || '—' }}</p>
      <div class="table-wrapper"><table class="data-table"><thead><tr><th>名册 ID</th><th>姓名</th><th>学号</th><th>档案 ID</th><th>操作</th></tr></thead>
        <tbody><tr v-for="row in classRoster" :key="row.id"><td>{{ row.id }}</td><td>{{ row.student_name }}</td><td>{{ row.student_no || '—' }}</td><td>{{ row.student_id ?? '未关联' }}</td>
          <td><button class="btn btn-secondary btn-sm" @click="beginRosterEdit(row)">纠正关联</button></td></tr><tr v-if="!classRoster.length"><td colspan="5" class="empty-cell">班级暂无名册</td></tr></tbody>
      </table></div>
      <form v-if="editRoster" class="correction-form" @submit.prevent="saveRosterLink">
        <strong>{{ editRoster.student_name }}（名册 #{{ editRoster.id }}）</strong>
        <label>Student 档案 ID<input v-model="editRoster.student_id_text" class="form-input" inputmode="numeric" placeholder="留空表示解除关联"></label>
        <button class="btn btn-primary">保存关联</button><button type="button" class="btn btn-ghost" @click="editRoster = null">取消</button>
      </form>
    </section>

    <section v-else-if="section === 'bindings'" class="card">
      <h2 class="card-header">家庭绑定与关系纠错</h2>
      <div class="table-wrapper"><table class="data-table"><thead><tr><th>学生</th><th>账号</th><th>关系</th><th>状态</th><th>操作</th></tr></thead>
        <tbody><tr v-for="row in rows" :key="row.student_id + ':' + row.user_id"><td>{{ row.student_name }}（{{ row.student_id }}）</td><td>{{ row.user_name }}（{{ row.user_id }}）</td><td>{{ row.relationship_label || row.relationship_type }}</td><td>{{ row.status }}</td><td><button class="btn btn-secondary btn-sm" @click="beginBindingEdit(row)">纠正</button></td></tr><tr v-if="!rows.length"><td colspan="5" class="empty-cell">暂无家庭绑定</td></tr></tbody>
      </table></div>
      <form v-if="editBinding" class="correction-form" @submit.prevent="saveBinding">
        <strong>{{ editBinding.student_name }} ↔ {{ editBinding.user_name }}</strong>
        <label>关系类型<select v-model="editBinding.relationship_type" class="form-select"><option value="self">本人</option><option value="father">父亲</option><option value="mother">母亲</option><option value="guardian">监护人</option><option value="other">其他</option></select></label>
        <label>关系备注<input v-model="editBinding.relationship_label" class="form-input" maxlength="80"></label>
        <label>状态<select v-model="editBinding.status" class="form-select"><option value="active">有效</option><option value="pending_review">待复核</option><option value="rejected">已拒绝</option><option value="removed">已解除</option></select></label>
        <button class="btn btn-primary">保存纠错</button><button type="button" class="btn btn-ghost" @click="editBinding = null">取消</button>
      </form>
    </section>

    <section v-else class="card">
      <h2 class="card-header">作业归属查询</h2>
      <p class="muted">展示作业任务与班级/学生/操作账号归属；不展示成绩排名。</p>
      <div class="table-wrapper"><table class="data-table"><thead><tr><th>任务</th><th>班级</th><th>学生档案</th><th>操作账号</th><th>作业</th><th>状态</th><th>创建时间</th></tr></thead>
        <tbody><tr v-for="row in rows" :key="row.task_id"><td>{{ row.task_id }}</td><td>{{ row.class_id ?? '—' }}</td><td>{{ row.student_id ?? '—' }}</td><td>{{ row.actor_user_id }}</td><td>{{ row.assignment_id ?? '—' }}</td><td>{{ row.status }}</td><td>{{ row.created_at ? new Date(row.created_at).toLocaleString() : '—' }}</td></tr><tr v-if="!rows.length"><td colspan="7" class="empty-cell">暂无作业记录</td></tr></tbody>
      </table></div>
    </section>
  </section>
</template>

<style scoped>
.platform-admin { display: grid; gap: 16px; }
.admin-heading, .admin-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
.admin-heading h1 { margin: 0; font-size: 1.6rem; }
.eyebrow { margin: 0 0 4px; color: #2563eb; font-size: .76rem; font-weight: 700; letter-spacing: .08em; }
.muted { color: #64748b; font-size: .86rem; }
.notice-message { padding: 10px 14px; border: 1px solid #a7f3d0; border-radius: 9px; color: #065f46; background: #ecfdf5; }
.admin-tabs { display: flex; gap: 6px; overflow-x: auto; border-bottom: 1px solid #dbe3ed; }
.admin-tabs button { padding: 11px 12px; color: #475569; white-space: nowrap; background: transparent; border-bottom: 2px solid transparent; }
.admin-tabs button.active { color: #1d4ed8; border-color: #2563eb; font-weight: 700; }
.search-box { display: grid; gap: 5px; width: min(360px, 100%); color: #64748b; font-size: .82rem; }
.teacher-create { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
.correction-form { display: flex; flex-wrap: wrap; align-items: end; gap: 10px; margin-top: 18px; padding: 14px; border: 1px solid #bfdbfe; border-radius: 9px; background: #f8fbff; }
.correction-form label { display: grid; gap: 5px; min-width: 150px; color: #475569; font-size: .82rem; }
.data-table { min-width: 650px; }
.empty-cell { padding: 24px; text-align: center; color: #94a3b8; }
@media (max-width: 760px) {
  .admin-heading, .admin-toolbar { align-items: stretch; flex-direction: column; }
  .teacher-create { grid-template-columns: 1fr; }
}
</style>
