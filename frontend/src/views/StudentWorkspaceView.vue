<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import { onBeforeRouteLeave } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import { studentApi, type LinkedStudent, type RosterOption, type StudentAssignment, type StudentBinding } from '@/api/student';
import { paperApi, type MistakeItem } from '@/api/paper';
import type { GradingResultResponse } from '@/api/homework';
import StudentWorkbench from '@/components/student/StudentWorkbench.vue';
import StudentStudyNavigation from '@/components/student/StudentStudyNavigation.vue';
import StudentPhotoSubmission from '@/components/student/StudentPhotoSubmission.vue';
import StudentFamilyConnection from '@/components/student/StudentFamilyConnection.vue';
import { assignmentFilters, assignmentGroup, assignmentReminders, dateLabel, deadlineTimestamp, gradeLabel, isReview, questionLabel, sortAssignments, subjectLabel, taskLabel, trustedQuestion, trustedSummary, type AssignmentFilter } from '@/student/workbench';
const auth = useAuthStore();
const students = ref<LinkedStudent[]>([]);
const selectedStudentId = ref<number | null>(null);
const binding = ref<StudentBinding | null>(null);
const bindingRequired = ref(false);
const assignments = ref<StudentAssignment[]>([]);
const mistakes = ref<MistakeItem[]>([]);
const resultReviewIds = ref<Set<string>>(new Set());
const mistakeError = ref(false);
const loadingMistakes = ref(false);
const subject = ref('');
const status = ref<AssignmentFilter>('all');
const search = ref('');
const highlightedAssignmentId = ref<number | null>(null);
const loading = ref(true);
const assignmentsLoaded = ref(false);
const familyCode = ref('');
const familyRelationship = ref('father');
const familyInviteCode = ref('');
const familyBusy = ref(false);
const error = ref('');
const notice = ref('');
const inviteCode = ref('');
const studentName = ref('');
const rosterOptions = ref<RosterOption[]>([]);
const selectedRosterId = ref<number | null>(null);
const bindingBusy = ref(false);
const activeAssignmentId = ref<number | null>(null);
const uploader = ref<{
    hasDraft: boolean;
    busy: boolean;
    unresolved?: boolean;
} | null>(null);
const result = ref<GradingResultResponse | null>(null);
const resultTaskId = ref('');
const resultBusy = ref(false);
const resultNotice = ref('');
const resultError = ref('');
const originalImages = ref<string[]>([]);
const imagesBusy = ref(false);
const paperDialog = ref<HTMLDialogElement | null>(null);
const paperUrl = ref('');
const paperBusy = ref(false);
const paperFormat = ref('');
const paperTitle = ref('');
const paperError = ref('');
const paperInline = ref(false);
let serial = 0;
let resultSerial = 0;
let paperSerial = 0;
const now = ref(Date.now());
let clock: ReturnType<typeof setInterval> | undefined;
const selectedStudent = computed(() => students.value.find(item => item.student_id === selectedStudentId.value));
const subjects = computed(() => [...new Set(assignments.value.map(item => item.subject).filter(Boolean))]);
const subjectCounts = computed(() => assignmentsLoaded.value ? assignments.value.reduce<Record<string, number>>((counts, item) => {
    counts[''] = (counts[''] || 0) + 1;
    if (item.subject) counts[item.subject] = (counts[item.subject] || 0) + 1;
    return counts;
}, { '': 0 }) : undefined);
const effectiveAssignments = computed(() => assignments.value.map(item => item.task_id && resultReviewIds.value.has(item.task_id) ? { ...item, task_status: 'HOLD_REVIEW' } : item));
const visibleAssignments = computed(() => sortAssignments(effectiveAssignments.value.filter(item => (!subject.value || item.subject === subject.value) && (status.value === 'all' || assignmentGroup(item) === status.value) && (!search.value.trim() || (item.title + ' ' + item.class_name).includes(search.value.trim())))));
const activeAssignment = computed(() => assignments.value.find(item => item.id === activeAssignmentId.value));
const todos = computed(() => effectiveAssignments.value.filter(item => assignmentGroup(item) === 'todo'));
const reviews = computed(() => effectiveAssignments.value.filter(item => assignmentGroup(item) === 'review'));
const reminders = computed(() => assignmentReminders(effectiveAssignments.value, now.value));
const openMistakes = computed(() => mistakes.value.filter(item => ['open', 'pending'].includes(item.status)));
const headingDate = computed(() => new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: 'long', day: 'numeric', weekday: 'long' }).format(new Date(now.value)));
const summaryVisible = computed(() => !!result.value && trustedSummary(result.value));
function clearFilters() { subject.value = ''; status.value = 'all'; search.value = ''; }
async function locateAssignment(item: StudentAssignment) {
    const studentId = selectedStudentId.value;
    clearFilters();
    highlightedAssignmentId.value = item.id;
    await nextTick();
    if (studentId !== selectedStudentId.value) return;
    const card = document.getElementById(`assignment-${item.id}`);
    card?.focus({ preventScroll: true });
    card?.scrollIntoView({ behavior: 'smooth', block: 'center' });
}
async function showReminder(group: AssignmentFilter) {
    clearFilters();
    status.value = group;
    await nextTick();
    document.getElementById('assignments-heading')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
function apiError(value: any, fallback: string) { return value?.response?.data?.detail || value?.response?.data?.message || value?.message || fallback; }
function mayDiscard(): boolean {
    if (uploader.value?.busy) {
        error.value = '作业正在提交，请等候提交结果后再操作。';
        return false;
    }
    return !uploader.value?.hasDraft || window.confirm(uploader.value?.unresolved
        ? '这份作业的提交结果尚未确认。离开后将丢失本次重试信息，请先重试或联系老师核实。仍要离开吗？'
        : '还有未提交的作业照片。离开会丢弃这些照片，是否继续？');
}
function beforeUnload(event: BeforeUnloadEvent) { if (uploader.value?.hasDraft || uploader.value?.busy) {
    event.preventDefault();
    event.returnValue = '';
} }
onBeforeRouteLeave(() => mayDiscard());
function revokeOriginals() { originalImages.value.forEach(url => URL.revokeObjectURL(url)); originalImages.value = []; }
function clearResult() { resultSerial += 1; result.value = null; resultTaskId.value = ''; resultNotice.value = ''; resultError.value = ''; resultBusy.value = false; revokeOriginals(); }
async function loadAssignments() {
    const studentId = selectedStudentId.value;
    const request = ++serial;
    mistakeError.value = false;
    if (!studentId) {
        assignments.value = [];
        mistakes.value = [];
        assignmentsLoaded.value = false;
        loadingMistakes.value = false;
        loading.value = false;
        return;
    }
    loading.value = true;
    error.value = '';
    void loadMistakes(studentId, request);
    try {
        const response = await studentApi.getAssignments(studentId);
        if (request !== serial)
            return;
        assignments.value = Array.isArray(response.data.data) ? response.data.data : [];
        assignmentsLoaded.value = true;
        if (!subjects.value.includes(subject.value))
            subject.value = '';
    }
    catch (err: any) {
        if (request === serial)
            error.value = apiError(err, '暂时无法读取作业，请重试。');
    }
    finally {
        if (request === serial)
            loading.value = false;
    }
}
async function loadMistakes(studentId: number, request: number) {
    loadingMistakes.value = true;
    try {
        const response = await paperApi.studentMistakes(studentId);
        if (request === serial)
            mistakes.value = response.items || [];
    }
    catch {
        if (request === serial)
            mistakeError.value = true;
    }
    finally {
        if (request === serial)
            loadingMistakes.value = false;
    }
}
async function loadWorkspace() {
    loading.value = true;
    error.value = '';
    try {
        if (auth.user?.role === 'student')
            binding.value = (await studentApi.getBinding()).data.data;
        students.value = ((await studentApi.getMyStudents()).data.data || []).filter(item => item.status === 'active');
        bindingRequired.value = auth.user?.role === 'student' && !binding.value?.is_bound && !students.value.length;
        selectedStudentId.value = students.value.some(item => item.student_id === binding.value?.student_id) ? binding.value!.student_id! : students.value.length === 1 ? students.value[0].student_id : null;
        if (!bindingRequired.value)
            await loadAssignments();
    }
    catch (err: any) {
        error.value = apiError(err, '读取学生身份失败，请重试。');
    }
    finally {
        loading.value = false;
    }
}
async function changeStudent(event: Event) {
    const element = event.target as HTMLSelectElement;
    if (!mayDiscard()) {
        element.value = String(selectedStudentId.value || '');
        return;
    }
    activeAssignmentId.value = null;
    highlightedAssignmentId.value = null;
    resultReviewIds.value = new Set();
    assignments.value = [];
    assignmentsLoaded.value = false;
    mistakes.value = [];
    clearResult();
    notice.value = '';
    subject.value = '';
    status.value = 'all';
    selectedStudentId.value = Number(element.value) || null;
    await loadAssignments();
}
async function refreshAssignments() {
    if (!mayDiscard())
        return;
    activeAssignmentId.value = null;
    await loadAssignments();
}
async function createFamilyInvite() {
    if (!selectedStudentId.value || familyBusy.value)
        return;
    familyBusy.value = true;
    error.value = '';
    try {
        familyInviteCode.value = (await studentApi.createFamilyInvite(selectedStudentId.value)).data.data.code;
    }
    catch (err: any) {
        error.value = apiError(err, '家庭邀请暂时无法生成。');
    }
    finally {
        familyBusy.value = false;
    }
}
async function claimFamilyInvite() {
    if (!familyCode.value.trim() || familyBusy.value || !mayDiscard())
        return;
    familyBusy.value = true;
    error.value = '';
    activeAssignmentId.value = null;
    clearResult();
    try {
        await studentApi.claimFamilyInvite(familyCode.value.trim(), familyRelationship.value);
        familyCode.value = '';
        await auth.refreshIdentity();
        await loadWorkspace();
        notice.value = '家庭关系已建立。';
    }
    catch (err: any) {
        error.value = apiError(err, '家庭关联失败，请核对邀请码。');
    }
    finally {
        familyBusy.value = false;
    }
}
async function findRoster() {
    error.value = '';
    notice.value = '';
    rosterOptions.value = [];
    selectedRosterId.value = null;
    if (!inviteCode.value.trim() || !studentName.value.trim()) {
        error.value = '请填写班级邀请码和学生姓名。';
        return;
    }
    bindingBusy.value = true;
    try {
        rosterOptions.value = (await studentApi.getBindingOptions(inviteCode.value.trim(), studentName.value.trim())).data.data.students || [];
        if (rosterOptions.value.length === 1)
            selectedRosterId.value = rosterOptions.value[0].id;
        if (!rosterOptions.value.length)
            notice.value = '没有找到可绑定的本人名册，请核对信息或联系老师。';
    }
    catch (err: any) {
        error.value = apiError(err, '名册查询失败。');
    }
    finally {
        bindingBusy.value = false;
    }
}
async function bindStudent() {
    if (!selectedRosterId.value || bindingBusy.value)
        return;
    bindingBusy.value = true;
    error.value = '';
    try {
        await studentApi.bind(inviteCode.value.trim(), studentName.value.trim(), selectedRosterId.value);
        await auth.refreshIdentity();
        await loadWorkspace();
        notice.value = '班级身份已绑定。';
    }
    catch (err: any) {
        error.value = apiError(err, '绑定失败，请核对本人名册。');
    }
    finally {
        bindingBusy.value = false;
    }
}
async function openSubmit(item: StudentAssignment) {
    if (activeAssignmentId.value === item.id) {
        await nextTick();
        document.getElementById('student-submission')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        return;
    }
    if (!mayDiscard())
        return;
    if ((item.submitted || item.task_id || isReview(item.task_status)) && item.task_status !== 'UNKNOWN_LAYOUT') {
        error.value = '这份作业已有提交，请查看原任务状态。';
        return;
    }
    if (item.variant_mode && !item.variant_available) {
        error.value = item.variant_message || '本次作业尚未就绪，请联系老师。';
        return;
    }
    error.value = '';
    clearResult();
    activeAssignmentId.value = item.id;
    await nextTick();
    document.getElementById('student-submission')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
function closeSubmission() { if (mayDiscard())
    activeAssignmentId.value = null; }
async function onSubmitted(response: {
    task_id: string;
    status: string;
    image_count: number;
}) {
    const item = activeAssignment.value;
    if (item) {
        item.submitted = true;
        item.task_id = response.task_id;
        item.task_status = response.status;
    }
    activeAssignmentId.value = null;
    notice.value = `已收到整份作业，共 ${response.image_count} 张照片。请保留任务编号：${response.task_id}。`;
    await nextTick();
    document.getElementById('submission-receipt')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    // The server receipt is authoritative even if the following list refresh fails.
    const id = selectedStudentId.value, request = serial;
    if (id) {
        try {
            const response = await studentApi.getAssignments(id);
            if (id === selectedStudentId.value && request === serial) {
                assignments.value = response.data.data || [];
                assignmentsLoaded.value = true;
            }
        }
        catch {
            if (id === selectedStudentId.value)
                notice.value += ' 作业列表暂未刷新，请稍后重试。';
        }
    }
}
async function showResult(taskId: string) {
    clearResult();
    const request = resultSerial;
    resultTaskId.value = taskId;
    resultBusy.value = true;
    try {
        const response = (await studentApi.getStatus(taskId)).data.data;
        if (request !== resultSerial)
            return;
        if (isReview(response.status))
            resultReviewIds.value.add(taskId);
        if (response.status !== 'SUCCESS') {
            resultNotice.value = isReview(response.status) ? '老师正在核对这份作业。复核完成前不计作错题，也不显示分数，无需重复提交。' : `${taskLabel(response.status)}。可稍后刷新查看。`;
            return;
        }
        const data = (await studentApi.getResult(taskId)).data.data;
        if (request !== resultSerial)
            return;
        if (!data.results?.length) {
            resultNotice.value = '暂时没有可展示的题目反馈，请联系老师。';
            return;
        }
        result.value = data;
        if (data.results.some(item => !trustedQuestion(item)))
            resultReviewIds.value.add(taskId);
        else
            resultReviewIds.value.delete(taskId);
        if (!trustedSummary(data))
            resultNotice.value = data.results.some(item => !trustedQuestion(item)) ? '部分题目仍待核对，暂不展示总分和正确率。' : '总分尚未确认，暂不展示总分和正确率。';
    }
    catch (err: any) {
        if (request === resultSerial)
            resultError.value = apiError(err, '暂时无法读取结果，请重试。');
    }
    finally {
        if (request === resultSerial) {
            resultBusy.value = false;
            await nextTick();
            document.getElementById('feedback-heading')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }
}
async function loadOriginalImages() {
    if (imagesBusy.value || !resultTaskId.value)
        return;
    const taskId = resultTaskId.value, request = resultSerial;
    imagesBusy.value = true;
    resultError.value = '';
    revokeOriginals();
    try {
        for (let index = 0; index < 9; index++) {
            try {
                const response = await studentApi.getOriginalImage(taskId, index);
                if (request !== resultSerial)
                    return;
                originalImages.value.push(URL.createObjectURL(response.data));
            }
            catch (err: any) {
                if (index > 0 && err.response?.status === 404)
                    break;
                throw err;
            }
        }
    }
    catch (err: any) {
        if (request === resultSerial)
            resultError.value = apiError(err, '读取本人作业照片失败。');
    }
    finally {
        imagesBusy.value = false;
    }
}
function closePaper() { paperSerial += 1; paperBusy.value = false; paperDialog.value?.close(); if (paperUrl.value)
    URL.revokeObjectURL(paperUrl.value); paperUrl.value = ''; }
async function openPaper(item: StudentAssignment) {
    closePaper();
    const request = paperSerial;
    paperTitle.value = item.title;
    paperFormat.value = (item.original_format || '').toLowerCase();
    paperError.value = '';
    paperInline.value = false;
    paperBusy.value = true;
    paperDialog.value?.showModal();
    const studentId = item.student_id || selectedStudentId.value;
    if (!studentId) {
        paperError.value = '请先选择本人学生身份。';
        paperBusy.value = false;
        return;
    }
    try {
        const response = await studentApi.getPublishedPaper(item.id, studentId);
        if (request !== paperSerial)
            return;
        const mime = response.data.type.split(';')[0];
        paperInline.value = (paperFormat.value === 'pdf' && mime === 'application/pdf') || (['png', 'jpg', 'jpeg'].includes(paperFormat.value) && ['image/png', 'image/jpeg'].includes(mime));
        paperUrl.value = URL.createObjectURL(response.data);
    }
    catch (err: any) {
        if (request === paperSerial)
            paperError.value = err.response?.status === 404 ? '试卷不存在或当前身份无权访问。' : err.response?.status === 409 ? '发布试卷版本需老师核对，请联系老师。' : '试卷暂时无法读取，请重试。';
    }
    finally {
        if (request === paperSerial)
            paperBusy.value = false;
    }
}
onMounted(() => { void loadWorkspace(); window.addEventListener('beforeunload', beforeUnload); clock = setInterval(() => { now.value = Date.now(); }, 60000); });
onBeforeUnmount(() => { serial++; clearResult(); closePaper(); window.removeEventListener('beforeunload', beforeUnload); if (clock)
    clearInterval(clock); });
</script>

<template>
  <div class="student-v1">
    <header class="page-header">
<div>
<p class="date-line">{{ headingDate }} · 学生学习工作台</p>
<h1>我的作业<span>{{ (selectedStudent?.classes || []).map(item => item.class_name).join(' · ') || '查看作业、完成练习、记录进步' }}</span>
</h1>
</div>
<label v-if="students.length" class="identity-picker">当前学生<select :value="selectedStudentId || ''" :disabled="uploader?.busy" @change="changeStudent">
<option value="">请选择本人身份</option>
<option v-for="item in students" :key="item.student_id" :value="item.student_id">{{ item.name }}{{ item.relationship_label ? `（${item.relationship_label}）` : '' }}</option>
</select>
</label>
</header>
    <p v-if="error" class="notice error" role="alert">{{ error }}</p>
<p v-if="notice" id="submission-receipt" class="notice success" role="status">{{ notice }}</p>
    <section v-if="bindingRequired" class="panel binding-panel">
<p class="eyebrow">开始学习之前</p>
<h2>找到你的班级身份</h2>
<p>填写老师提供的邀请码和本人姓名。查询后，请确认选择的是你本人。</p>
<div class="binding-fields">
<label>班级邀请码<input v-model="inviteCode" autocomplete="off" maxlength="12" />
</label>
<label>学生姓名<input v-model="studentName" autocomplete="name" maxlength="100" />
</label>
<button :disabled="bindingBusy" @click="findRoster">{{ bindingBusy ? '查询中…' : '查询本人名册' }}</button>
</div>
<fieldset v-if="rosterOptions.length">
<legend>确认本人名册</legend>
<label v-for="item in rosterOptions" :key="item.id">
<input v-model="selectedRosterId" type="radio" :value="item.id" />{{ item.student_name }}<span v-if="item.student_no"> · 学号 {{ item.student_no }}</span>
</label>
<button :disabled="!selectedRosterId || bindingBusy" @click="bindStudent">确认绑定</button>
</fieldset>
<StudentFamilyConnection v-model:code="familyCode" v-model:relationship="familyRelationship" :can-invite="!!selectedStudentId" :busy="familyBusy" :invite-code="familyInviteCode" @create="createFamilyInvite" @claim="claimFamilyInvite" />
</section>
    <StudentWorkbench v-else>
      <template #navigation>
        <StudentStudyNavigation v-model="subject" page="assignments" :subjects="subjects" :counts="subjectCounts" />
        <StudentFamilyConnection v-model:code="familyCode" v-model:relationship="familyRelationship" :can-invite="!!selectedStudentId" :busy="familyBusy" :invite-code="familyInviteCode" @create="createFamilyInvite" @claim="claimFamilyInvite" />
      </template>
      <section class="panel assignments-panel" aria-labelledby="assignments-heading">
        <div class="section-heading">
<div>
<h2 id="assignments-heading">作业清单 <span class="section-subject">{{ subject ? subjectLabel(subject) : '全部学科' }}</span><span v-if="assignmentsLoaded" class="list-count">{{ visibleAssignments.length }} 份</span></h2>
</div>
<button class="text-button" :disabled="loading || !!uploader?.busy" @click="refreshAssignments">{{ loading ? '读取中…' : '刷新列表' }}</button>
</div>
        <nav class="status-tabs" aria-label="作业状态筛选">
          <button v-for="item in assignmentFilters" :key="item.value" type="button" :aria-pressed="status === item.value" @click="status=item.value">{{ item.label }}</button>
        </nav>
        <div class="filters">
<label class="search"><span class="sr-only">搜索作业</span><input v-model="search" placeholder="搜索作业标题或班级" type="search" />
</label>
<button v-if="subject || status !== 'all' || search" class="text-button" @click="clearFilters">清除筛选</button>
</div>
        <p v-if="loading" class="empty" role="status">正在读取本人作业…</p>
<p v-else-if="!selectedStudentId" class="empty">请先选择已绑定的学生身份。</p>
<p v-else-if="!visibleAssignments.length && !error" class="empty">当前范围没有作业。可以试试其他学科或状态。</p>
        <div v-else class="assignment-list">
<article v-for="item in visibleAssignments" :id="`assignment-${item.id}`" :key="`${item.id}-${item.student_id}`" tabindex="-1" class="assignment-card" :class="{ highlighted: highlightedAssignmentId===item.id }" :aria-labelledby="`assignment-title-${item.id}`">
<div class="assignment-overview">
  <div class="assignment-info">
    <div class="card-top"><span class="subject-pill">{{ subjectLabel(item.subject) }}</span><span class="status-pill" :class="assignmentGroup(item)">{{ assignmentGroup(item) === 'todo' ? '待提交' : taskLabel(item.task_status) }}</span></div>
    <h3 :id="`assignment-title-${item.id}`">{{ item.title }}</h3>
    <p class="meta">{{ item.class_name }}<template v-if="item.grade"> · {{ gradeLabel(item.grade) }}</template></p>
    <p class="deadline" :class="{overdue: assignmentGroup(item)==='todo' && (deadlineTimestamp(item.due_at) ?? Infinity) < now}"><span v-if="assignmentGroup(item)==='todo' && (deadlineTimestamp(item.due_at) ?? Infinity) < now">已过截止 · </span>截止：{{ dateLabel(item.due_at) }}</p>
  </div>
</div>
<details v-if="item.description || (item.variant_mode && item.variant_available && item.variant_questions?.length)" class="requirements">
<summary>查看作业说明<template v-if="item.variant_mode && item.variant_available && item.variant_questions?.length">与题目要求 · {{ item.variant_questions.length }} 题</template></summary>
<p v-if="item.description" class="description">{{ item.description }}</p>
<ol v-if="item.variant_mode && item.variant_available && item.variant_questions?.length">
<li v-for="question in item.variant_questions" :key="question.id">
<span class="requirement" :class="{optional:question.requirement==='optional'}">{{ question.requirement === 'optional' ? '选做' : question.requirement === 'required' ? '必做' : '要求待老师确认' }}</span>第 {{ question.number }} 题 · {{ question.question_text }}<ul v-if="question.options?.length">
<li v-for="(option,index) in question.options" :key="index">{{ option }}</li>
</ul>
</li>
</ol>
</details>
<p v-if="item.variant_mode && !item.variant_available" class="muted">{{ item.variant_message || '作业版本尚未就绪，请联系老师。' }}</p>
<div class="card-actions">
<button v-if="assignmentGroup(item)==='todo' || item.task_status==='UNKNOWN_LAYOUT'" :disabled="!!uploader?.busy || (item.variant_mode && !item.variant_available)" @click="openSubmit(item)">{{ item.task_status==='UNKNOWN_LAYOUT' ? '核对后重新拍照' : '拍照提交' }}</button>
<button v-if="item.task_id" :class="{ secondary: item.task_status==='UNKNOWN_LAYOUT' }" :disabled="resultBusy" @click="showResult(item.task_id)">{{ assignmentGroup(item)==='completed' ? '查看批改反馈' : '查看处理进度' }}</button>
<button v-if="item.assignment_mode==='uniform_mixed'" class="secondary" @click="openPaper(item)">查看试卷 / 打印</button>
<span v-if="assignmentGroup(item)==='review'" class="action-note">等待核对，无需重复提交</span>
</div>
</article>
</div>
      </section>
      <StudentPhotoSubmission v-if="activeAssignment && selectedStudentId" id="student-submission" :key="`${activeAssignment.id}-${selectedStudentId}`" ref="uploader" :assignment="activeAssignment" :student-id="selectedStudentId" @submitted="onSubmitted" @cancel="closeSubmission" />
      <section v-if="resultTaskId" class="panel feedback" aria-labelledby="feedback-heading">
<div class="section-heading">
<h2 id="feedback-heading">作业反馈</h2>
<button class="text-button" :disabled="resultBusy" @click="showResult(resultTaskId)">刷新进度</button>
</div>
<p class="muted">{{ assignments.find(item => item.task_id === resultTaskId)?.title || resultTaskId }}</p>
<p v-if="resultBusy" role="status">正在读取作业状态…</p>
<p v-if="resultNotice" class="review-notice" role="status">{{ resultNotice }}</p>
<p v-if="resultError" class="notice error" role="alert">{{ resultError }}</p>
<template v-if="result">
<div v-if="summaryVisible" class="score">
<strong>{{ result.total_score }}<small> / {{ result.total_max_score }} 分</small>
</strong>
<span v-if="typeof result.total_accuracy === 'number' && Number.isFinite(result.total_accuracy) && result.total_accuracy >= 0 && result.total_accuracy <= 100">正确率 {{ Math.round(result.total_accuracy) }}%</span>
</div>
<article v-for="item in result.results" :key="item.question_block_id" class="question-feedback">
<div>
<strong>第 {{ item.question_no }} 题</strong>
<span>{{ questionLabel(item.result) }}</span>
</div>
<p>{{ item.question_text }}</p>
<p v-if="item.student_answer">我的作答：{{ item.student_answer }}</p>
<p v-if="trustedQuestion(item)" class="muted">得分 {{ item.score }} / {{ item.max_score }}</p>
<p v-else class="muted">待老师核对，暂不显示分数。</p>
</article>
<button class="secondary" :disabled="imagesBusy" @click="loadOriginalImages">{{ imagesBusy ? '读取照片中…' : '查看本人作业照片' }}</button>
<div class="original-images">
<img v-for="(url,index) in originalImages" :key="url" :src="url" :alt="`本人第 ${index+1} 张作业照片`" />
</div>
</template>
</section>
      <template #reminders>
        <section class="reminder-card">
<p class="eyebrow">接下来做什么</p>
<h2>我的待办</h2>
<div class="reminder-counts">
<button class="reminder-count" @click="showReminder('todo')">
<span>待提交作业</span>
<strong>{{ assignmentsLoaded ? todos.length : '—' }}</strong>
</button>
<button class="reminder-count" @click="showReminder('review')">
<span>等待老师复核</span>
<strong>{{ assignmentsLoaded ? reviews.length : '—' }}</strong>
</button>
</div>
<p class="muted">点击提醒可定位到对应作业。</p>
</section>
        <section v-if="reminders.attention.length" class="reminder-card priority-card">
<h2>优先处理 <span class="list-count">{{ reminders.attention.length }}</span></h2>
<button v-for="item in reminders.attention.slice(0,3)" :key="item.id" class="deadline-item" :aria-label="`定位作业：${item.title}`" @click="locateAssignment(item)">
<span>{{ item.title }} <span aria-hidden="true">↗</span></span>
<small>{{ assignmentGroup(item)==='todo' ? `已过截止 · ${dateLabel(item.due_at)}` : taskLabel(item.task_status) }}</small>
</button>
</section>
        <section class="reminder-card">
<h2>近期截止</h2>
<p v-if="!assignmentsLoaded" class="muted">作业列表尚未读取成功。</p>
<p v-else-if="!reminders.upcoming.length" class="muted">暂无已确认截止时间的即将到期作业。</p>
<button v-for="item in reminders.upcoming.slice(0,3)" :key="item.id" class="deadline-item" :aria-label="`定位作业：${item.title}`" @click="locateAssignment(item)">
<span>{{ item.title }} <span aria-hidden="true">↗</span></span>
<small>{{ dateLabel(item.due_at) }}</small>
</button>
</section>
        <section v-if="reminders.review.length" class="reminder-card">
<h2>待老师复核 <span class="list-count">{{ reminders.review.length }}</span></h2>
<button v-for="item in reminders.review.slice(0,2)" :key="item.id" class="deadline-item" :aria-label="`定位作业：${item.title}`" @click="locateAssignment(item)">
<span>{{ item.title }} <span aria-hidden="true">↗</span></span><small>等待核对，无需重复提交</small>
</button>
<button v-if="reminders.review.length>2" class="text-button" @click="showReminder('review')">查看全部待复核 →</button>
</section>
        <section class="reminder-card">
<p class="eyebrow">错题待办</p>
<h2>待订正错题</h2>
<p v-if="!selectedStudentId" class="muted">请先选择本人学生身份。</p>
<p v-else-if="loadingMistakes" class="muted">正在读取错题…</p>
<p v-else-if="mistakeError" class="muted">错题待办暂不可用，请到错题库重试。</p>
<p v-else class="muted">{{ openMistakes.length ? `${openMistakes.length} 道题等待订正` : '当前没有待订正的错题。' }}</p>
<router-link class="side-link" to="/student/mistakes">进入我的错题库 →</router-link>
</section>
        <p class="quiet-note">选做题由你决定是否挑战，未作答不代表做错。</p>
      </template>
    </StudentWorkbench>
    <dialog ref="paperDialog" class="paper-dialog" aria-labelledby="paper-heading" @cancel="closePaper">
<header class="section-heading">
<h2 id="paper-heading">{{ paperTitle }}</h2>
<button class="secondary" @click="closePaper">关闭试卷</button>
</header>
<p v-if="paperBusy" role="status">正在读取正式发布的试卷…</p>
<p v-if="paperError" class="notice error" role="alert">{{ paperError }}</p>
<template v-if="paperUrl">
<p class="muted">打开试卷窗口后，可使用 PDF 打印图标或浏览器打印（Ctrl+P）。</p>
<div class="paper-actions">
<a v-if="paperInline" :href="paperUrl" target="_blank" rel="noopener noreferrer">打开试卷 / 打印</a>
<a :href="paperUrl" :download="`${paperTitle}.${paperFormat || 'pdf'}`">下载试卷</a>
</div>
<iframe v-if="paperInline && paperFormat==='pdf'" :src="paperUrl" title="正式发布试卷预览">
</iframe>
<img v-else-if="paperInline" :src="paperUrl" alt="正式发布的试卷" />
<p v-else class="muted">此格式不支持浏览器预览，请下载后使用对应软件打开并打印。</p>
</template>
</dialog>
  </div>
</template>
<style scoped>
.student-v1{container-type:inline-size;color:#263d32;max-width:1600px;margin:0 auto;padding:6px 0 34px;min-width:0}
.page-header{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:20px}
.date-line,.eyebrow{color:#6d8275;font-size:12px;letter-spacing:.06em;margin:0 0 10px}
.page-header h1{font-size:28px;margin:0;letter-spacing:-.04em}
.page-header h1 span{display:block;margin-top:8px;font-size:13px;font-weight:400;letter-spacing:0;color:#7b8a80}
.identity-picker{font-size:12px;display:grid;gap:8px;min-width:160px}
.panel,.reminder-card{background:#fff;border:1px solid #e1e8e1;border-radius:14px;padding:20px;min-width:0}
.panel{margin-bottom:20px}
.section-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}
.section-heading h2,.reminder-card h2{font-size:17px;margin:0;font-weight:650}
.assignments-panel{container-type:inline-size;padding:16px 18px}
.section-subject{font-size:11px;font-weight:400;color:#75887a;margin-left:8px}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.reminder-card{padding:16px}
.reminder-card h2{margin-bottom:10px;font-size:15px}
.list-count{font-size:12px;font-weight:400;color:#75887a;margin-left:7px}
.student-v1 .status-tabs{display:flex;gap:13px;flex-wrap:wrap;border-bottom:1px solid #e4ebe5}
.student-v1 .status-tabs button{border:0;border-bottom:2px solid transparent;border-radius:0;background:transparent;color:#708176;padding:8px 0;font-size:12px}
.student-v1 .status-tabs button[aria-pressed=true]{border-color:#185d49;color:#185d49;font-weight:650}
.student-v1 button:focus-visible,.student-v1 a:focus-visible{outline:3px solid #9ec7b6;outline-offset:2px}
.student-v1 button{border:1px solid #185d49;background:#185d49;color:#fff;border-radius:9px;cursor:pointer;padding:10px 15px;font:inherit;font-size:13px}
.student-v1 button:disabled{opacity:.45;cursor:not-allowed}
.student-v1 .secondary{background:#fff;color:#365d49;border-color:#d3dfd7}
.student-v1 .text-button{background:transparent;color:#527565;border:0;padding:4px;font-size:12px}
.student-v1 input,.student-v1 select{border:1px solid #d8e1da;background:#fff;border-radius:8px;padding:9px 11px;min-height:39px;font:inherit;font-size:13px;color:#365140;box-sizing:border-box;max-width:100%}
.filters{display:flex;align-items:center;gap:10px;margin-top:10px;padding-bottom:10px;border-bottom:1px solid #edf0eb}
.filters input{min-height:34px;padding:7px 10px}
.filters label{display:grid;gap:7px;font-size:12px;color:#7a897e}
.filters select{min-width:140px}
.search{flex:1}
.assignment-list{display:grid;margin-top:0}
.assignment-card{border:0;border-bottom:1px solid #e4e9e1;border-radius:0;padding:13px 2px;background:#fff;scroll-margin:24px;min-width:0}
.assignment-card:last-child{border-bottom:0;padding-bottom:0}
.assignment-card:focus-visible{outline:2px solid #81b09a;outline-offset:5px;border-radius:6px}
.assignment-card.highlighted{background:#f2f8f3;box-shadow:0 0 0 7px #f2f8f3;border-radius:6px}
.assignment-overview{min-width:0}
.assignment-info{min-width:0}
.card-top{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.assignment-info>.meta{font-size:11px;margin:2px 0 0}
.subject-pill,.status-pill{font-size:11px;padding:5px 10px;border-radius:6px;background:#eff4f1;color:#56705e}
.subject-pill{padding:3px 7px}
.status-pill{background:#f4f3ed;color:#81765c;line-height:1.5;padding:3px 7px}
.status-pill.review{background:#fcf4df;color:#8e723a}
.status-pill.completed{background:#e7f3ea;color:#376d4a}
.status-pill.attention{background:#fbedeb;color:#a7574c}
.assignment-card h3{font-size:16px;margin:7px 0 4px;line-height:1.5;overflow-wrap:anywhere}
.meta,.description,.deadline,.muted{font-size:12px;line-height:1.8;color:#7b8b80}
.description{white-space:pre-line}
.deadline{margin:3px 0 0;font-size:11px}
.deadline.overdue{color:#a95a47}
.card-actions,.paper-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;align-items:center}
.card-actions button{padding:7px 11px;font-size:12px;min-height:33px}
.action-note{font-size:11px;color:#8a784e;line-height:1.6}
.requirements{font-size:13px;color:#57725d;border-radius:8px;margin-top:7px}
.requirements[open]{background:#f6f8f4;padding:10px}
.requirements summary{cursor:pointer;font-size:12px;line-height:1.8}
.requirements ol{padding-left:20px}
.requirements li{padding:6px 0;line-height:1.8}
.requirement{display:inline-block;margin-right:8px;background:#e3eee4;padding:0 6px;border-radius:4px;font-size:11px}
.requirement.optional{background:#f5eedc;color:#8b764b}
.reminder-counts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
.student-v1 .reminder-count{display:grid;gap:5px;width:100%;padding:8px;border:1px solid #e2eae2;border-radius:8px;background:#f7faf7;color:#5a7061;text-align:left;font-size:11px}
.reminder-count strong{font-size:22px;font-weight:500;color:#214a35}
.reminder-counts+.muted{font-size:11px;margin:8px 0 0}
.student-v1 .deadline-item{display:grid;gap:4px;text-align:left;width:100%;padding:9px 0;background:transparent;border:0;border-bottom:1px solid #edf1eb;color:#36583f;line-height:1.6;font-size:12px}
.deadline-item>span{display:flex;justify-content:space-between;gap:5px}
.deadline-item small{font-size:11px;color:#8d9387}
.priority-card{border-color:#eadbc8;background:#fffcf6}
.priority-card .deadline-item small{color:#996548}
.side-link{color:#326f51;text-decoration:none;font-size:13px;display:inline-block;margin-top:10px}
.quiet-note{color:#8b998d;font-size:11px;line-height:1.8;padding:0 10px}
.notice{border-radius:9px;padding:14px;font-size:13px;line-height:1.8;overflow-wrap:anywhere;margin:0 0 18px}
.error{background:#fff1ee;color:#9b453c}
.success{background:#eaf4eb;color:#39714a}
.empty{padding:35px 4px;color:#849186;font-size:13px;text-align:center}
.review-notice{padding:14px;background:#fff8e8;border-radius:8px;color:#8c7547;font-size:13px;line-height:1.8}
.score{display:flex;justify-content:space-between;align-items:center;margin:25px 0;color:#2e6248}
.score strong{font-size:35px}
.score small,.score span{font-size:13px;font-weight:400;color:#7f9286}
.question-feedback{border-top:1px solid #e5eae4;padding:20px 0;font-size:13px}
.question-feedback>div{display:flex;justify-content:space-between;gap:12px}
.question-feedback>div span{color:#8f7c4f;font-size:12px}
.question-feedback p{line-height:1.8}
.original-images img{width:100%;margin-top:14px;object-fit:contain}
.paper-dialog{width:min(1000px,94vw);max-height:94dvh;border:1px solid #d3dfd7;border-radius:16px;padding:24px;color:#365140;box-sizing:border-box}
.paper-dialog::backdrop{background:rgb(19 35 26 / 60%)}
.paper-dialog iframe{width:100%;height:65dvh;border:1px solid #d3dfd7;margin-top:16px}
.paper-dialog img{max-width:100%;display:block;margin:20px auto}
.paper-actions a{padding:10px 15px;border:1px solid #c6d6cb;border-radius:8px;color:#27613f;text-decoration:none;font-size:13px}
.binding-fields{display:flex;align-items:end;gap:14px;flex-wrap:wrap;margin-top:24px}
.binding-fields label{display:grid;gap:8px;font-size:13px}
.binding-panel p{font-size:13px;line-height:1.8;color:#6c8271}
.binding-panel fieldset{margin-top:24px;border:1px solid #d3dfd7;border-radius:10px;display:grid;gap:14px;padding:16px}
.binding-panel fieldset label{font-size:14px;display:flex;align-items:center;gap:8px}
@container(min-width:470px){
  .assignment-card{display:grid;grid-template-columns:minmax(0,1fr) 138px;column-gap:14px;align-items:center}
  .assignment-overview,.requirements,.assignment-card>.muted{grid-column:1}
  .card-actions{grid-column:2;grid-row:1 / span 3;display:grid;gap:6px;margin:0}
  .card-actions button{width:100%}
  .action-note{text-align:center}
}
@container(max-width:650px){.page-header{align-items:start;flex-direction:column;gap:12px}
.page-header h1{font-size:26px}
.identity-picker{width:100%}
.panel{padding:17px}
.score{flex-wrap:wrap;gap:12px}
}
@container(max-width:280px){
  .filters{flex-direction:column;align-items:stretch}
  .section-heading{align-items:start;flex-wrap:wrap}
  .card-actions button{width:100%}
}

</style>
