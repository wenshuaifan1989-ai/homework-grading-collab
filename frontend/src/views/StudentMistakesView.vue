<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { paperApi, type MistakeItem } from '@/api/paper'
import { studentApi, type LinkedStudent } from '@/api/student'
import StudentWorkbench from '@/components/student/StudentWorkbench.vue'
import StudentStudyNavigation from '@/components/student/StudentStudyNavigation.vue'
import StudentMistakePrint from '@/components/student/StudentMistakePrint.vue'
import { assignmentMistakes, identityIssue, mistakeSubject, orderedSubjects, singleStudent, studentExperience, validMistakeReceipt, type StudentMistakeMaterial } from '@/student/experience'
import { subjectLabel } from '@/student/workbench'
import { safeQuestionImage, type MistakePrintSelection } from '@/student/mistakePrint'

const students = ref<LinkedStudent[]>([])
const studentId = ref<number | null>(null)
const mistakes = ref<MistakeItem[]>([])
const deleted = ref<MistakeItem[]>([])
const subject = ref('')
const recycleBin = ref(false)
const selectedIds = ref<Set<number>>(new Set())
const materials = ref<Record<number, StudentMistakeMaterial>>({})
const materialErrors = ref<Record<number, string>>({})
const loadingMaterials = ref(false)
const printOpen = ref(false)
const printSelection = ref<MistakePrintSelection[]>([])
const detailDialog = ref<HTMLDialogElement | null>(null)
const detailItem = ref<MistakeItem | null>(null)
const detailKind = ref<'own' | 'standard'>('own')
const detailOwnText = ref('')
const detailImage = ref('')
const detailBusy = ref(false)
const detailError = ref('')
const detailTriggerId = ref('')
const pendingAction = ref<{ id: number; deleted: boolean; key: string } | null>(null)
const confirmDeleteId = ref<number | null>(null)
const loading = ref(false)
const loaded = ref(false)
const busyId = ref<number | null>(null)
const error = ref('')
const notice = ref('')
let serial = 0
let detailSerial = 0

const subjects = computed(() => orderedSubjects([...mistakes.value, ...deleted.value]))
const shownItems = computed(() => recycleBin.value ? deleted.value : mistakes.value)
const subjectCounts = computed(() => shownItems.value.reduce<Record<string, number>>((counts, item) => {
  const code = mistakeSubject(item); counts[code] = (counts[code] || 0) + 1; return counts
}, {}))
const groups = computed(() => assignmentMistakes(shownItems.value, subject.value))
const visibleItems = computed(() => groups.value.flatMap(group => group.items).filter(item => item.student_id === studentId.value))
const shownCount = computed(() => visibleItems.value.length)
const selectionCount = computed(() => visibleItems.value.filter(item => selectedIds.value.has(item.id)).length)
const allSelected = computed(() => !!visibleItems.value.length && selectionCount.value === visibleItems.value.length)
const partiallySelected = computed(() => selectionCount.value > 0 && !allSelected.value)
const canDelete = computed(() => !!studentExperience.changeMistake && !!studentExperience.deletedMistakes)
const detailAnswer = computed(() => detailItem.value ? publicAnswer(detailItem.value) : '')
function apiError(err: any, fallback: string): string { return err?.response?.data?.detail || err?.response?.data?.message || err?.message || fallback }
function canLeave() {
  if (busyId.value !== null) { error.value = '操作正在提交，请等候结果后再离开。'; return false }
  if (pendingAction.value) { error.value = '上一项删除或恢复尚未确认，请先用原操作重试。'; return false }
  return true
}
onBeforeRouteLeave(canLeave)
function beforeUnload(event: BeforeUnloadEvent) {
  if (busyId.value !== null || pendingAction.value) { event.preventDefault(); event.returnValue = '' }
}
function clearDetail() {
  detailSerial++
  if (detailImage.value) URL.revokeObjectURL(detailImage.value)
  detailImage.value = ''; detailOwnText.value = ''; detailBusy.value = false; detailError.value = ''
  detailItem.value = null
  detailDialog.value?.close()
}
async function closeDetail() {
  const trigger = detailTriggerId.value
  clearDetail()
  await nextTick()
  document.getElementById(trigger)?.focus()
}
function clearSelection() {
  selectedIds.value = new Set(); printOpen.value = false; printSelection.value = []
  clearDetail(); confirmDeleteId.value = null
}
function setSubject(value: string) {
  if (value === subject.value || !canLeave()) return
  clearSelection(); subject.value = value
}
function toggleRecycleBin() {
  if (!canDelete.value || !canLeave()) return
  clearSelection(); recycleBin.value = !recycleBin.value
}
function toggleAll() {
  if (recycleBin.value || loading.value || busyId.value !== null) return
  selectedIds.value = allSelected.value ? new Set() : new Set(visibleItems.value.map(item => item.id))
}
function toggleItem(item: MistakeItem) {
  if (recycleBin.value || loading.value || busyId.value !== null || !visibleItems.value.some(row => row.id === item.id)) return
  const next = new Set(selectedIds.value)
  if (next.has(item.id)) next.delete(item.id); else next.add(item.id)
  selectedIds.value = next
}
function materialFor(item: MistakeItem): StudentMistakeMaterial | null {
  const material = materials.value[item.id]
  return item.student_id === studentId.value && material?.student_id === studentId.value && material.mistake_id === item.id ? material : null
}
function publicAnswer(item: MistakeItem): string {
  const answer = materialFor(item)?.standard_answer
  return answer?.released === true && typeof answer.text === 'string' ? answer.text.trim() : ''
}
function answerHint(item: MistakeItem): string {
  if (loadingMaterials.value) return '正在核对标准答案的公开权限'
  if (materialErrors.value[item.id]) return materialErrors.value[item.id]
  return publicAnswer(item) ? '查看老师已公开的标准答案' : '标准答案暂未公开或尚未提供'
}
function questionText(item: MistakeItem): string { return materialFor(item)?.question?.text || item.question?.question_text || '题干资料待提供' }
function questionImage(item: MistakeItem): string | null { return safeQuestionImage(materialFor(item)?.question?.image_data_url) }
function questionOptions(item: MistakeItem): string[] {
  const options = materialFor(item)?.question?.options ?? item.question?.options
  if (Array.isArray(options)) return options.filter(value => typeof value === 'string')
  if (options && typeof options === 'object') return Object.entries(options).map(([key, value]) => `${key}. ${value}`)
  return []
}
// Only the explicitly supplied student adapter establishes answer publication and clean question material.
async function loadMaterials(items: MistakeItem[], id: number, request: number) {
  const provider = studentExperience.mistakeMaterial
  materials.value = {}; materialErrors.value = {}
  if (!provider) { loadingMaterials.value = false; return }
  loadingMaterials.value = true
  const results = await Promise.all(items.map(async item => {
    try {
      const material = await provider(id, item.id)
      if (!material || material.student_id !== id || material.mistake_id !== item.id) throw Error('题目资料与当前学生不一致')
      return { id: item.id, material, message: '' }
    } catch (err: any) { return { id: item.id, material: null, message: apiError(err, '标准答案暂不可查看') } }
  }))
  if (request !== serial || studentId.value !== id) return
  const next: Record<number, StudentMistakeMaterial> = {}, issues: Record<number, string> = {}
  for (const result of results) {
    if (result.material) next[result.id] = result.material
    else issues[result.id] = result.message
  }
  materials.value = next; materialErrors.value = issues; loadingMaterials.value = false
}
async function loadStudents() {
  if (!canLeave()) return
  const request = ++serial
  clearSelection(); materials.value = {}; loading.value = true; error.value = ''; studentId.value = null
  try {
    const response = await studentApi.getMyStudents()
    if (request !== serial) return
    students.value = (response.data.data || []).filter(item => item.status === 'active')
    studentId.value = singleStudent(students.value)?.student_id || null
    if (studentId.value) await loadMistakes()
    else { mistakes.value = []; deleted.value = []; error.value = identityIssue(students.value) }
  } catch (err: any) { if (request === serial) error.value = apiError(err, '读取学生身份失败，请重试。') }
  finally { if (request === serial) loading.value = false }
}
async function loadMistakes() {
  clearSelection()
  const id = studentId.value, request = ++serial
  materials.value = {}; materialErrors.value = {}; loadingMaterials.value = false
  if (!id) { mistakes.value = []; deleted.value = []; loaded.value = false; return }
  loading.value = true; error.value = ''
  try {
    const [active, removed] = await Promise.all([
      paperApi.studentMistakes(id),
      studentExperience.deletedMistakes ? studentExperience.deletedMistakes(id) : Promise.resolve([]),
    ])
    if (request !== serial || studentId.value !== id) return
    mistakes.value = (active.items || []).filter(item => item.student_id === id)
    deleted.value = (removed || []).filter(item => item.student_id === id)
    loaded.value = true
    const available = orderedSubjects([...mistakes.value, ...deleted.value])
    if (!available.includes(subject.value)) subject.value = available[0] || ''
    await loadMaterials([...mistakes.value, ...deleted.value], id, request)
  } catch (err: any) { if (request === serial) error.value = apiError(err, '错题库暂时无法读取，请重试。') }
  finally { if (request === serial) loading.value = false }
}
function refreshMistakes() { if (canLeave()) return loadMistakes() }
async function showDetail(item: MistakeItem, kind: 'own' | 'standard') {
  if (!visibleItems.value.some(row => row.id === item.id) || (kind === 'standard' && !publicAnswer(item))) return
  clearDetail(); detailItem.value = item; detailKind.value = kind
  const request = detailSerial, id = studentId.value
  detailTriggerId.value = `mistake-${item.id}-${kind}`
  const ownText = materialFor(item)?.student_answer
  detailOwnText.value = typeof ownText === 'string' ? ownText.trim() : ''
  await nextTick()
  if (request !== detailSerial || studentId.value !== id || detailItem.value?.id !== item.id) return
  detailDialog.value?.showModal()
  if (kind === 'own' && !detailOwnText.value) await showOwnImage('crop')
}
async function showOwnImage(kind: 'crop' | 'original') {
  const item = detailItem.value, id = studentId.value
  if (!item || detailKind.value !== 'own' || !id) return
  const request = ++detailSerial
  if (detailImage.value) URL.revokeObjectURL(detailImage.value)
  detailImage.value = ''; detailBusy.value = true; detailError.value = ''
  try {
    const blob = await paperApi.image(kind === 'crop' ? item.crop_url : item.original_url, kind)
    if (request !== detailSerial || studentId.value !== id || detailItem.value?.id !== item.id) return
    if (!['image/png', 'image/jpeg', 'image/gif', 'image/bmp'].includes(blob.type.split(';')[0] || '')) throw Error('本人作答图片格式暂不支持，请联系老师核对。')
    detailImage.value = URL.createObjectURL(blob)
  } catch (err: any) { if (request === detailSerial) detailError.value = apiError(err, '本人作答暂时无法读取，请重试。') }
  finally { if (request === detailSerial) detailBusy.value = false }
}
function openPrint() {
  if (recycleBin.value || loading.value || loadingMaterials.value || !selectionCount.value || busyId.value !== null) return
  printSelection.value = visibleItems.value.filter(item => selectedIds.value.has(item.id)).map(item => ({ item, material: materialFor(item) }))
  printOpen.value = true
}
async function closePrint() { printOpen.value = false; printSelection.value = []; await nextTick(); document.getElementById('mistake-print-entry')?.focus() }
function newActionKey() { return typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `student-${Date.now()}-${Math.random().toString(36).slice(2)}` }
function askDelete(item: MistakeItem) {
  if (!canDelete.value || busyId.value !== null || item.student_id !== studentId.value || pendingAction.value) return
  confirmDeleteId.value = item.id; notice.value = ''; error.value = ''
}
async function changeMistake(item: MistakeItem, shouldDelete: boolean) {
  const id = studentId.value, request = serial
  if (!id || item.student_id !== id || !canDelete.value || busyId.value !== null) return
  if (shouldDelete && confirmDeleteId.value !== item.id && pendingAction.value?.id !== item.id) return
  const pending = pendingAction.value
  if (pending && (pending.id !== item.id || pending.deleted !== shouldDelete)) { error.value = '上一项操作结果还未确认，请先用原操作重试。'; return }
  const action = pending || { id: item.id, deleted: shouldDelete, key: newActionKey() }
  pendingAction.value = action; busyId.value = item.id; error.value = ''; notice.value = ''
  try {
    const receipt = await studentExperience.changeMistake!(id, item.id, shouldDelete, action.key)
    if (studentId.value !== id || request !== serial) return
    if (!validMistakeReceipt(receipt, id, item.id, shouldDelete)) throw Error('服务端回执与错题不一致，请联系老师核对。')
    if (shouldDelete) { mistakes.value = mistakes.value.filter(row => row.id !== item.id); deleted.value = [...deleted.value, item] }
    else { deleted.value = deleted.value.filter(row => row.id !== item.id); mistakes.value = [...mistakes.value, item] }
    pendingAction.value = null; confirmDeleteId.value = null
    notice.value = shouldDelete ? '已移到回收站，可随时恢复。' : '错题已恢复。'
    await loadMistakes()
  } catch (err: any) { error.value = `${apiError(err, '网络异常')} 操作结果尚未确认；请保留本页，用同一操作重试。` }
  finally { busyId.value = null }
}
onMounted(() => { void loadStudents(); window.addEventListener('beforeunload', beforeUnload) })
onBeforeUnmount(() => { serial++; clearDetail(); window.removeEventListener('beforeunload', beforeUnload) })
</script>

<template>
  <section class="mistake-workspace">
    <header class="page-header"><p class="eyebrow">学生学习工作台 · 按作业回顾</p><h1>我的错题库</h1><p class="muted">一次查看一个学科，按作业选择题目。</p></header>
    <p v-if="error" class="notice error" role="alert">{{ error }}</p>
    <p v-if="notice" class="notice success" role="status">{{ notice }}</p>
    <StudentWorkbench>
      <template #navigation><StudentStudyNavigation :model-value="subject" page="mistakes" :subjects="subjects" :counts="subjectCounts" @update:model-value="setSubject" /></template>
      <section class="panel library-heading">
        <div><p class="eyebrow">{{ recycleBin ? '可恢复记录' : '错题索引' }}</p><h2>{{ subject ? subject==='__unconfirmed__' ? '学科待核对' : subjectLabel(subject) : '请选择学科' }} · {{ recycleBin ? '回收站' : '按作业归类' }}</h2><p v-if="loaded" class="muted">{{ shownCount }} 道题，{{ groups.length }} 份作业</p></div>
        <div class="heading-actions"><button type="button" :disabled="loading || busyId!==null || !!pendingAction" @click="refreshMistakes">刷新</button><button type="button" :disabled="!canDelete || busyId!==null || !!pendingAction" @click="toggleRecycleBin">{{ recycleBin ? '返回错题库' : '回收站' }}</button></div>
      </section>
      <div v-if="!recycleBin && shownCount" class="selection-toolbar">
        <label class="select-all"><input type="checkbox" :checked="allSelected" :indeterminate="partiallySelected" :disabled="loading || busyId!==null" @change="toggleAll" />全选当前学科</label>
        <span class="selection-count" aria-live="polite">已选 {{ selectionCount }} 题</span>
        <button id="mistake-print-entry" type="button" class="primary" :disabled="!selectionCount || loading || loadingMaterials || busyId!==null" @click="openPrint">下载 / 打印</button>
      </div>
      <p v-if="loading" class="empty" role="status">{{ loadingMaterials ? '正在核对题面和标准答案权限…' : '正在读取本人错题…' }}</p>
      <p v-else-if="!studentId" class="empty">{{ identityIssue(students) }}</p>
      <p v-else-if="!subject" class="empty">目前没有已归类的错题学科。</p>
      <p v-else-if="!groups.length && !error" class="empty">{{ recycleBin ? '这个学科的回收站为空。' : '这个学科暂无错题。' }}</p>
      <section v-for="group in groups" :key="group.key" class="assignment-group" :aria-label="group.title">
        <header class="group-header"><h2>{{ group.title }}</h2><span>{{ group.items.length }} 题</span></header>
        <article v-for="item in group.items" :key="item.id" class="panel mistake-card" :class="{ selected: !recycleBin && selectedIds.has(item.id) }">
          <div class="question-heading"><label v-if="!recycleBin" class="question-check"><input type="checkbox" :aria-label="`选择${group.title}第${item.question_no || '待核对'}题`" :checked="selectedIds.has(item.id)" :disabled="loading || busyId!==null" @change="toggleItem(item)" /></label><p class="question-index">{{ group.title }} · 第 {{ item.question_no || '待核对' }} 题</p></div>
          <h3>{{ questionText(item) }}</h3>
          <ol v-if="questionOptions(item).length" class="options"><li v-for="(option,index) in questionOptions(item)" :key="index">{{ option }}</li></ol>
          <img v-if="questionImage(item)" class="clean-question-image" :src="questionImage(item)!" alt="题目配图" />
          <div class="actions"><button :id="`mistake-${item.id}-own`" type="button" @click="showDetail(item,'own')">查看作答</button><button :id="`mistake-${item.id}-standard`" type="button" :disabled="!publicAnswer(item)" :title="answerHint(item)" @click="showDetail(item,'standard')">查看标准答案</button>
            <button v-if="!recycleBin" type="button" class="delete-button" :disabled="!canDelete || busyId!==null || !!pendingAction" :title="canDelete ? '移入回收站，可恢复' : '可恢复删除暂不可用'" @click="askDelete(item)">删除错题</button>
            <button v-else type="button" :disabled="busyId!==null || (!!pendingAction && pendingAction.id!==item.id)" @click="changeMistake(item,false)">{{ pendingAction?.id===item.id ? '用原操作重试恢复' : '恢复错题' }}</button>
          </div>
          <div v-if="!recycleBin && (confirmDeleteId===item.id || (pendingAction?.id===item.id && pendingAction.deleted))" class="delete-confirm" role="group" :aria-label="`删除第 ${item.question_no || '待核对'} 题`"><p>移入回收站后可以恢复，原作业与历史记录保留。</p><button type="button" :disabled="busyId!==null" @click="changeMistake(item,true)">{{ pendingAction?.id===item.id ? '用原操作重试' : '确认删除' }}</button><button type="button" :disabled="busyId!==null || !!pendingAction" @click="confirmDeleteId=null">取消</button></div>
        </article>
      </section>
      <template #reminders><section class="reminder-card"><p class="eyebrow">所属作业</p><h2>{{ subject ? subject==='__unconfirmed__' ? '学科待核对' : subjectLabel(subject) : '选择学科' }}</h2><ul v-if="groups.length" class="group-links"><li v-for="group in groups" :key="group.key">{{ group.title }} · {{ group.items.length }} 题</li></ul><p v-else class="muted">选择学科后显示关联作业。</p><p class="muted">先全选，再取消不需要的题目，即可打印部分错题。</p></section></template>
    </StudentWorkbench>
    <dialog ref="detailDialog" class="detail-dialog" aria-labelledby="mistake-detail-title" @cancel.prevent="closeDetail">
      <header class="dialog-heading"><div><p class="eyebrow">{{ detailItem?.assignment_title }} · 第 {{ detailItem?.question_no || '待核对' }} 题</p><h2 id="mistake-detail-title">{{ detailKind==='own' ? '本人作答' : '标准答案' }}</h2></div><button type="button" @click="closeDetail">返回错题</button></header>
      <template v-if="detailKind==='standard'"><p v-if="detailAnswer" class="answer-text">{{ detailAnswer }}</p><p v-else class="muted">标准答案暂未公开或尚未提供。</p></template>
      <template v-else><p v-if="detailOwnText" class="answer-text">{{ detailOwnText }}</p><p v-if="detailBusy" role="status">正在读取本人作答…</p><p v-if="detailError" class="notice error" role="alert">{{ detailError }}</p><img v-if="detailImage" class="evidence" :src="detailImage" alt="本人作业中的作答" /><div class="actions"><button type="button" :disabled="detailBusy" @click="showOwnImage('crop')">查看作答图片</button><button type="button" :disabled="detailBusy" @click="showOwnImage('original')">查看原始作业页</button></div></template>
    </dialog>
    <StudentMistakePrint v-if="printOpen && studentId" :student-id="studentId" :subject="subject" :selection="printSelection" @close="closePrint" />
  </section>
</template>

<style scoped>
.detail-dialog{margin:auto}
.mistake-workspace{color:#294a39;min-width:0}.page-header{margin-bottom:20px}.page-header h1{font-size:28px;margin:0}.page-header>.muted{margin-bottom:0}.eyebrow{color:#637e6c;font-size:11px;letter-spacing:.06em;margin:0 0 8px}.muted{color:#66786e;font-size:13px;line-height:1.7}.panel,.reminder-card{background:#fff;border:1px solid #dce8dd;border-radius:14px;padding:20px;margin-bottom:16px;min-width:0}.library-heading,.dialog-heading{display:flex;justify-content:space-between;gap:16px;align-items:center}.library-heading h2{font-size:20px;margin:0}.heading-actions,.actions{display:flex;gap:8px;flex-wrap:wrap}.actions{margin-top:20px}button{border:1px solid #c5d8ca;border-radius:8px;background:#fff;color:#185d49;padding:9px 13px;font:inherit;font-size:12px;cursor:pointer;min-height:38px}button.primary{background:#185d49;color:#fff;border-color:#185d49}button:disabled{opacity:.45;cursor:not-allowed}button:focus-visible,a:focus-visible,input:focus-visible{outline:3px solid #9ec7b6;outline-offset:2px}.notice{border-radius:9px;padding:12px;font-size:12px;line-height:1.7}.notice.error{background:#fff1f0;color:#922}.notice.success{background:#e8f5e9;color:#185d49}.empty{padding:24px;color:#617769;background:#fff;border-radius:12px}.selection-toolbar{display:flex;align-items:center;gap:16px;flex-wrap:wrap;padding:14px 16px;background:#edf5ef;border:1px solid #d4e4d8;border-radius:10px;margin:16px 0}.select-all{display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer}.selection-count{font-size:12px;color:#66786e;margin-right:auto}.selection-toolbar input,.question-check input{width:18px;height:18px;accent-color:#185d49}.assignment-group{margin:24px 0}.group-header{display:flex;align-items:center;gap:12px;padding:0 4px 10px}.group-header h2{font-size:17px;margin:0}.group-header span{font-size:12px;color:#7a897e}.mistake-card.selected{border-color:#84b698;background:#fcfffc;box-shadow:0 0 0 1px #84b698}.question-heading{display:flex;align-items:center;gap:10px}.question-check{display:flex;cursor:pointer}.question-index{color:#6b8273;font-size:12px;margin:0;line-height:1.7}.mistake-card h3{font-size:17px;line-height:1.8;white-space:pre-wrap;margin:16px 0 0;font-weight:500;overflow-wrap:anywhere}.options{font-size:14px;line-height:1.8;padding-left:22px}.clean-question-image{display:block;max-width:100%;max-height:320px;object-fit:contain;margin-top:16px}.delete-button{color:#a23737;border-color:#e3c1c1;margin-left:auto}.delete-confirm{border:1px solid #e2c5bb;background:#fff9f5;border-radius:8px;padding:12px;margin-top:12px;font-size:12px;line-height:1.7}.delete-confirm button{margin-right:8px}.reminder-card h2{font-size:16px;margin:0}.group-links{padding-left:18px;font-size:12px;line-height:1.9}.detail-dialog{width:min(740px,calc(100vw - 28px));max-height:90dvh;overflow:auto;box-sizing:border-box;border:1px solid #bfd6c8;border-radius:16px;padding:24px;color:#294a39;background:#fff}.detail-dialog::backdrop{background:#19352e70}.dialog-heading h2{font-size:21px;margin:0}.answer-text{white-space:pre-wrap;overflow-wrap:anywhere;font-size:16px;line-height:1.9;padding:18px;background:#f3f8f3;border-radius:9px}.evidence{display:block;max-width:100%;max-height:60dvh;object-fit:contain;margin:18px auto}@media(max-width:600px){.library-heading,.dialog-heading{align-items:flex-start;flex-direction:column}.panel,.reminder-card{padding:16px}.selection-toolbar{gap:10px}.delete-button{margin-left:0}.detail-dialog{padding:18px}}
@media(pointer:coarse),(max-width:700px){button{min-height:44px;font-size:14px}.select-all,.question-check{min-height:44px}.question-check{min-width:44px;justify-content:center}.question-heading{gap:4px}.select-all{padding-right:8px}.heading-actions{width:100%}.selection-toolbar{gap:8px 12px}.group-header{align-items:flex-start}.group-header h2{overflow-wrap:anywhere}.group-header span{flex-shrink:0}}
@media(max-width:600px){.page-header h1{font-size:25px}.detail-dialog{width:100%;max-width:none;max-height:100dvh;height:100dvh;margin:0;border-radius:0;border:0;padding:18px;padding-top:max(18px,env(safe-area-inset-top));padding-bottom:max(24px,env(safe-area-inset-bottom))}.dialog-heading{flex-direction:row;position:sticky;top:calc(-1 * max(18px,env(safe-area-inset-top)));padding:12px 0;background:#fff;z-index:1}.dialog-heading>div{min-width:0}.dialog-heading>button{flex-shrink:0}.actions button{flex:1 1 auto}.selection-toolbar>.primary{min-width:120px}.evidence{max-height:none;width:100%;height:auto}}
</style>
