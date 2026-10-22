<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { onBeforeRouteLeave } from 'vue-router';
import { paperApi, type MistakeItem } from '@/api/paper';
import { studentApi, type LinkedStudent } from '@/api/student';
import StudentWorkbench from '@/components/student/StudentWorkbench.vue';
import StudentStudyNavigation from '@/components/student/StudentStudyNavigation.vue';
import StudentProfilePanel from '@/components/student/StudentProfilePanel.vue';
import { useAuthStore } from '@/stores/auth';
import type { ProfileMetric } from '@/student/profile';
import { mistakeLabel, subjectLabel, trustedQuestion } from '@/student/workbench';
const students = ref<LinkedStudent[]>([]);
const auth = useAuthStore();
const studentId = ref<number | null>(null);
const mistakes = ref<MistakeItem[]>([]);
const subject = ref('');
const knowledge = ref('');
const dateFilter = ref('');
const state = ref('todo');
const drafts = ref<Record<number, string>>({});
const history = ref<Record<number, Array<Record<string, any>>>>({});
const historyOpen = ref<Record<number, boolean>>({});
const historyError = ref<Record<number, string>>({});
const historyBusy = ref<Record<number, boolean>>({});
const evidence = ref<Record<string, string>>({});
const imageKind = ref<Record<number, 'crop' | 'original'>>({});
const imageBusy = ref<Record<number, boolean>>({});
const selected = ref<Set<number>>(new Set());
const reviewDialog = ref<HTMLDialogElement | null>(null);
const loading = ref(false);
const mistakesLoaded = ref(false);
const busyId = ref<number | null>(null);
const error = ref('');
const notice = ref('');
let serial = 0;
const subjects = computed(() => [...new Set(mistakes.value.map(item => item.subject).filter(Boolean))] as string[]);
const subjectCounts = computed(() => mistakesLoaded.value ? mistakes.value.reduce<Record<string, number>>((counts, item) => {
    counts[''] = (counts[''] || 0) + 1;
    if (item.subject) counts[item.subject] = (counts[item.subject] || 0) + 1;
    return counts;
}, { '': 0 }) : undefined);
const knowledgePoints = computed(() => [...new Set(mistakes.value.flatMap(item => item.knowledge_points || []))].sort());
const visibleMistakes = computed(() => mistakes.value.filter(item => (!subject.value || item.subject === subject.value) && (!dateFilter.value || item.created_at?.slice(0, 10) === dateFilter.value) && (!knowledge.value || (knowledge.value === '__unclassified__' ? !item.knowledge_points?.length : item.knowledge_points?.includes(knowledge.value))) && (state.value === 'all' || (state.value === 'todo' && ['open', 'pending'].includes(item.status)) || (state.value === 'review' && item.status === 'correction_submitted') || (state.value === 'done' && item.status === 'mastered'))));
const reviewItems = computed(() => mistakes.value.filter(item => selected.value.has(item.id)));
const pendingCount = computed(() => mistakes.value.filter(item => ['open', 'pending'].includes(item.status)).length);
const reviewCount = computed(() => mistakes.value.filter(item => item.status === 'correction_submitted').length);
const doneCount = computed(() => mistakes.value.filter(item => item.status === 'mastered').length);
const hasFilters = computed(() => !!subject.value || !!knowledge.value || !!dateFilter.value || state.value !== 'all');
const selectedStudent = computed(() => students.value.find(item => item.student_id === studentId.value));
const profileMetrics = computed<ProfileMetric[]>(() => selectedStudent.value ? [
    { label: '待订正错题', value: mistakesLoaded.value ? pendingCount.value : null, unit: '题' },
    { label: '待老师审核', value: mistakesLoaded.value ? reviewCount.value : null, unit: '题' },
    { label: '老师已审核', value: mistakesLoaded.value ? doneCount.value : null, unit: '题' },
] : []);
function clearFilters() { subject.value = ''; knowledge.value = ''; dateFilter.value = ''; state.value = 'all'; }
function apiError(err: any, fallback: string) { return err?.response?.data?.detail || err?.response?.data?.message || fallback; }
function hasDraft() { return Object.values(drafts.value).some(value => value.trim()); }
function canLeave() { if (busyId.value !== null) {
    error.value = '订正正在提交，请等候结果后再操作。';
    return false;
} return !hasDraft() || window.confirm('还有未提交的订正内容。离开会丢弃草稿，是否继续？'); }
onBeforeRouteLeave(canLeave);
function beforeUnload(event: BeforeUnloadEvent) { if (hasDraft() || busyId.value !== null) {
    event.preventDefault();
    event.returnValue = '';
} }
function clearEvidence() { Object.values(evidence.value).forEach(url => URL.revokeObjectURL(url)); evidence.value = {}; imageKind.value = {}; }
async function loadStudents() { loading.value = true; error.value = ''; try {
    students.value = ((await studentApi.getMyStudents()).data.data || []).filter(item => item.status === 'active');
    studentId.value = students.value.length === 1 ? students.value[0].student_id : null;
    if (studentId.value)
        await loadMistakes();
}
catch (err: any) {
    error.value = apiError(err, '读取学生身份失败，请重试。');
}
finally {
    loading.value = false;
} }
async function loadMistakes() { const id = studentId.value, request = ++serial; if (!id) {
    mistakes.value = [];
    mistakesLoaded.value = false;
    loading.value = false;
    return;
} loading.value = true; error.value = ''; try {
    const response = await paperApi.studentMistakes(id);
    if (request !== serial)
        return;
    mistakes.value = response.items || [];
        mistakesLoaded.value = true;
    selected.value = new Set([...selected.value].filter(key => mistakes.value.some(item => item.id === key)));
    if (subject.value && !subjects.value.includes(subject.value))
        subject.value = '';
}
catch (err: any) {
    if (request === serial)
        error.value = apiError(err, '错题库暂时无法读取，请重试。');
}
finally {
    if (request === serial)
        loading.value = false;
} }
async function selectStudent(event: Event) { const element = event.target as HTMLSelectElement; if (!canLeave()) {
    element.value = String(studentId.value || '');
    return;
} serial++; studentId.value = Number(element.value) || null; mistakes.value = []; mistakesLoaded.value = false; drafts.value = {}; history.value = {}; historyOpen.value = {}; historyError.value = {}; selected.value = new Set(); clearEvidence(); subject.value = ''; knowledge.value = ''; dateFilter.value = ''; state.value = 'todo'; notice.value = ''; await loadMistakes(); }
async function showImage(item: MistakeItem, kind: 'crop' | 'original') { const key = `${item.id}:${kind}`, id = studentId.value; if (imageBusy.value[item.id])
    return; imageKind.value[item.id] = kind; if (evidence.value[key])
    return; imageBusy.value[item.id] = true; error.value = ''; try {
    const blob = await paperApi.image(kind === 'crop' ? item.crop_url : item.original_url, kind);
    if (studentId.value !== id)
        return;
    evidence.value[key] = URL.createObjectURL(blob);
}
catch (err: any) {
    if (studentId.value === id)
        error.value = apiError(err, '本人作答图片暂时无法读取。');
}
finally {
    imageBusy.value[item.id] = false;
} }
async function loadHistory(item: MistakeItem) { const id = studentId.value; historyBusy.value[item.id] = true; historyError.value[item.id] = ''; try {
    const response = await paperApi.correctionHistory(item.id);
    if (studentId.value === id)
        history.value[item.id] = response.items || [];
}
catch (err: any) {
    if (studentId.value === id)
        historyError.value[item.id] = apiError(err, '订正记录读取失败，请重试。');
}
finally {
    historyBusy.value[item.id] = false;
} }
async function toggleHistory(item: MistakeItem) { historyOpen.value[item.id] = !historyOpen.value[item.id]; if (historyOpen.value[item.id])
    await loadHistory(item); }
async function submitCorrection(item: MistakeItem) { if (busyId.value !== null)
    return; const answer = (drafts.value[item.id] || '').trim(); if (!answer) {
    error.value = '请先写下你的订正答案。';
    return;
} busyId.value = item.id; error.value = ''; notice.value = ''; try {
    await paperApi.submitCorrection(item.id, answer);
    drafts.value[item.id] = '';
    notice.value = '订正已提交，等待老师审核。原始成绩和历史记录保留。';
    await loadMistakes();
    if (historyOpen.value[item.id])
        await loadHistory(item);
}
catch (err: any) {
    error.value = apiError(err, '订正提交失败，草稿已保留，请重试。');
}
finally {
    busyId.value = null;
} }
async function markMastered(item: MistakeItem) { if (busyId.value !== null)
    return; busyId.value = item.id; error.value = ''; notice.value = ''; try {
    await paperApi.markMastered(item.id);
    notice.value = '已记录自评掌握，仍以老师审核结果为准。';
    await loadMistakes();
    if (historyOpen.value[item.id])
        await loadHistory(item);
}
catch (err: any) {
    error.value = apiError(err, '暂时无法记录自评掌握，请重试。');
}
finally {
    busyId.value = null;
} }
function selectForReview(item: MistakeItem, event: Event) { if ((event.target as HTMLInputElement).checked)
    selected.value.add(item.id);
else
    selected.value.delete(item.id); }
onMounted(() => { void loadStudents(); window.addEventListener('beforeunload', beforeUnload); });
onBeforeUnmount(() => { serial++; clearEvidence(); window.removeEventListener('beforeunload', beforeUnload); });
</script>
<template>
  <section class="mistake-workspace">
    <header class="page-header">
<div>
<p class="eyebrow">学生学习工作台 · 回顾与订正</p>
<h1>我的错题库</h1>
<p class="muted">回看原题与本人作答，订正后查看老师审核记录。</p>
</div>
<div class="header-controls">
<div class="page-account-actions">
<label class="identity-picker">学生身份<select :value="studentId || ''" :disabled="busyId!==null" @change="selectStudent">
<option value="">选择已绑定学生</option>
<option v-for="item in students" :key="item.student_id" :value="item.student_id">{{ item.name }}</option>
</select></label>
<StudentProfilePanel :account="auth.user" :student="selectedStudent" :metrics="profileMetrics" :disabled="busyId!==null" />
</div>
<router-link to="/student">返回我的作业 →</router-link>
</div>
</header>
    <p v-if="error" class="notice error" role="alert">{{ error }}</p>
<div v-if="notice" class="notice success" role="status"><span>{{ notice }}</span><button v-if="notice.startsWith('订正已提交') && state!=='review'" class="text-button" @click="state='review'">查看待老师审核</button></div>
    <StudentWorkbench>
      <template #navigation>
        <StudentStudyNavigation v-model="subject" page="mistakes" :subjects="subjects" :counts="subjectCounts" />
      </template>
      <section class="panel filter-panel">
<div class="section-heading">
<div>
<h2>错题与订正 <span class="section-subject">{{ subject ? subjectLabel(subject) : '全部学科' }}</span><span v-if="mistakesLoaded" class="list-count">{{ visibleMistakes.length }} 题</span></h2>
</div>
<button class="text-button" :disabled="loading || busyId!==null" @click="loadMistakes">刷新错题</button>
</div>
<nav class="mistake-tabs" aria-label="错题状态筛选">
<button type="button" :aria-pressed="state==='todo'" @click="state='todo'">待订正 <span>{{ mistakesLoaded ? pendingCount : '—' }}</span></button>
<button type="button" :aria-pressed="state==='review'" @click="state='review'">待老师审核 <span>{{ mistakesLoaded ? reviewCount : '—' }}</span></button>
<button type="button" :aria-pressed="state==='done'" @click="state='done'">老师已审核 <span>{{ mistakesLoaded ? doneCount : '—' }}</span></button>
<button type="button" :aria-pressed="state==='all'" @click="state='all'">全部错题 <span>{{ mistakesLoaded ? mistakes.length : '—' }}</span></button>
</nav>
<div class="filter-tools">
<details class="advanced-filters">
<summary>知识点与日期筛选<span v-if="knowledge || dateFilter" class="active-filters">已筛选</span></summary>
<div class="filters">
<label>知识点<select v-model="knowledge">
<option value="">全部知识点</option>
<option value="__unclassified__">待归类</option>
<option v-for="point in knowledgePoints" :key="point" :value="point">{{ point }}</option>
</select>
</label>
<label>日期<input v-model="dateFilter" type="date" />
</label>
</div>
</details>
<button v-if="hasFilters" type="button" class="text-button" @click="clearFilters">清除筛选</button>
</div>
<p v-if="knowledge || dateFilter" class="filter-summary">当前条件：<span v-if="knowledge">{{ knowledge==='__unclassified__' ? '知识点待归类' : knowledge }}</span><span v-if="dateFilter">{{ dateFilter }}</span></p>
</section>
      <p v-if="loading" class="empty" role="status">正在读取本人错题…</p>
<p v-else-if="!studentId" class="empty">请先选择已绑定的学生身份。</p>
<div v-else-if="!visibleMistakes.length && !error" class="empty"><p>{{ state==='todo' ? '当前范围没有待订正错题，可以查看待老师审核或全部错题。' : '当前范围暂无错题，可以调整筛选条件。' }}</p><button v-if="hasFilters" type="button" class="text-button" @click="clearFilters">查看全部错题</button></div>
      <article v-for="item in visibleMistakes" :key="item.id" class="panel mistake-card">
<div class="card-top">
<span class="subject-pill">{{ subjectLabel(item.subject) }}</span>
<span class="status-pill">{{ mistakeLabel(item.status) }}</span>
</div>
<p class="source-label">{{ item.assignment_title || '原作业' }} · 第 {{ item.question_no || '待核对' }} 题</p>
<h2>{{ item.question?.question_text || '题面待老师核对' }}</h2>
<ul v-if="item.question?.options" class="options">
<li v-for="(option,key) in item.question.options" :key="key">{{ option }}</li>
</ul>
<div v-if="item.knowledge_points?.length" class="knowledge-chips">
<span v-for="point in item.knowledge_points" :key="point">{{ point }}</span>
</div>
<p v-else class="muted">知识点待归类</p>
<p v-if="item.grading_result?.student_answer" class="own-answer">我的作答：{{ item.grading_result.student_answer }}</p>
<p v-if="trustedQuestion(item.grading_result)" class="muted">本次得分 {{ item.grading_result!.score }} / {{ item.grading_result!.max_score }}</p>
<p v-else class="muted">判分待老师核对，暂不显示分数。</p>
<div class="actions">
<button class="secondary" :disabled="imageBusy[item.id]" @click="showImage(item,'crop')">查看原题与作答</button>
<button class="secondary" :disabled="imageBusy[item.id]" @click="showImage(item,'original')">查看本人原始作业页</button>
</div>
<img v-if="evidence[`${item.id}:${imageKind[item.id]||'crop'}`]" class="evidence" :src="evidence[`${item.id}:${imageKind[item.id]||'crop'}`]" alt="本人作业证据" />
<label class="correction-field">我的订正<textarea v-model="drafts[item.id]" :disabled="busyId===item.id" rows="3" placeholder="写下重新思考后的答案与过程" />
</label>
<div class="actions">
<button :disabled="busyId!==null" @click="submitCorrection(item)">{{ busyId===item.id ? '正在提交…' : '提交订正' }}</button>
<button class="secondary" :disabled="busyId!==null" @click="markMastered(item)">自评已掌握</button>
<button class="text-button" :disabled="historyBusy[item.id]" @click="toggleHistory(item)">订正与审核记录</button>
</div>
<label class="review-choice">
<input type="checkbox" :checked="selected.has(item.id)" @change="selectForReview(item,$event)" />加入本次复习清单</label>
<section v-if="historyOpen[item.id]" class="history">
<p v-if="historyBusy[item.id]" role="status">正在读取记录…</p>
<p v-else-if="historyError[item.id]" class="notice error" role="alert">{{ historyError[item.id] }}</p>
<p v-else-if="!history[item.id]?.length" class="muted">还没有订正记录。</p>
<article v-for="attempt in history[item.id] || []" :key="attempt.id">
<strong>{{ attempt.attempt_type==='mark_mastered' ? '自评掌握' : '订正' }} · {{ mistakeLabel(attempt.status) }}</strong>
<p v-if="attempt.submitted_answer">我的订正：{{ attempt.submitted_answer }}</p>
<p v-if="attempt.review_feedback">老师反馈：{{ attempt.review_feedback }}</p>
<small>{{ attempt.created_at?.replace('T',' ') }}</small>
</article>
</section>
</article>
      <template #reminders>
<section class="reminder-card">
<p class="eyebrow">学习待办</p>
<h2>订正进度</h2>
<p class="count-line">
<span>待订正</span>
<strong>{{ mistakesLoaded ? pendingCount : '—' }}</strong>
</p>
<p class="count-line">
<span>待老师审核</span>
<strong>{{ mistakesLoaded ? reviewCount : '—' }}</strong>
</p>
<p class="muted">自评掌握与老师审核是两件事。订正不会覆盖原始成绩。</p>
</section>
<section class="reminder-card">
<p class="eyebrow">本次复习</p>
<h2>我的复习清单</h2>
<p class="muted">从原题中选几道，再认真练习一次。</p>
<button class="review-button" :disabled="!reviewItems.length" @click="reviewDialog?.showModal()">查看清单（{{ reviewItems.length }}）</button>
<p class="small-note">本清单只在当前页面保留，离开或刷新后需重新选择。</p>
</section>
</template>
    </StudentWorkbench>
    <dialog ref="reviewDialog" class="review-dialog" aria-labelledby="review-heading">
<header class="section-heading">
<h2 id="review-heading">本次复习清单 · {{ reviewItems.length }} 题</h2>
<button class="secondary" @click="reviewDialog?.close()">关闭清单</button>
</header>
<p class="muted">请回看原题，在纸上独立作答，再对照允许查看的反馈。</p>
<ol>
<li v-for="item in reviewItems" :key="item.id">
<span>{{ subjectLabel(item.subject) }} · 第 {{ item.question_no || '待核对' }} 题</span>
<p>{{ item.question?.question_text || '题面待老师核对' }}</p>
<small>{{ item.assignment_title || '原作业' }}</small>
</li>
</ol>
</dialog>
  </section>
</template>
<style scoped>
.mistake-workspace{container-type:inline-size;color:#263d32;max-width:1600px;min-width:0;margin:0 auto;padding:6px 0 34px}
.page-header{display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:20px}
.eyebrow{font-size:12px;color:#7c8e80;letter-spacing:.06em;margin:0 0 10px}
.page-header h1{font-size:28px;margin:0}
.header-controls{display:grid;gap:9px;min-width:160px}
.header-controls>a{color:#456c54;text-decoration:none;font-size:12px;text-align:right}
.identity-picker{display:grid;gap:7px;font-size:12px;color:#6b806e}
.page-account-actions{display:flex;align-items:end;gap:10px;flex-wrap:wrap}
.page-account-actions .identity-picker{min-width:160px;flex:1}
.muted{font-size:13px;line-height:1.8;color:#7a8e7e}
.panel,.reminder-card{border:1px solid #e0e8df;border-radius:14px;background:#fff;padding:20px;margin-bottom:18px;min-width:0}
.reminder-card{margin:0}
.section-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}
.section-heading h2,.reminder-card h2{font-size:17px;margin:0}
.list-count{font-size:12px;font-weight:400;color:#75887a;margin-left:7px}
.section-subject{font-size:11px;font-weight:400;color:#75887a;margin-left:7px}
.filter-panel{padding:16px 18px}
.mistake-workspace button:focus-visible,.mistake-workspace a:focus-visible,.mistake-workspace summary:focus-visible,.mistake-workspace select:focus-visible,.mistake-workspace input:focus-visible,.mistake-workspace textarea:focus-visible{outline:3px solid #9ec7b6;outline-offset:2px}
.mistake-workspace .mistake-tabs{display:flex;gap:12px;flex-wrap:wrap;border-bottom:1px solid #e4ebe5}
.mistake-workspace .mistake-tabs button{padding:8px 0;border:0;border-bottom:2px solid transparent;border-radius:0;background:transparent;color:#708176;font-size:12px}
.mistake-workspace .mistake-tabs button[aria-pressed=true]{color:#185d49;border-bottom-color:#185d49;font-weight:650}
.mistake-tabs span{margin-left:4px;font-size:11px}
.filter-tools{display:flex;align-items:start;justify-content:space-between;gap:10px;margin-top:11px}
.advanced-filters{flex:1;min-width:0;font-size:12px;color:#637e69}
.advanced-filters summary{cursor:pointer;line-height:2}
.active-filters{font-size:11px;color:#185d49;background:#e7f3ea;border-radius:4px;padding:2px 5px;margin-left:7px}
.filter-summary{font-size:11px;line-height:1.8;color:#637e69;margin:8px 0 0;overflow-wrap:anywhere}
.filter-summary span{margin-right:8px}
.filters{display:flex;gap:12px;margin-top:10px;flex-wrap:wrap}
.filters label{display:grid;gap:8px;flex:1;font-size:12px;min-width:130px;color:#6b806e}
.mistake-workspace select,.mistake-workspace input[type=date],.mistake-workspace textarea{font:inherit;font-size:13px;box-sizing:border-box;padding:10px;border:1px solid #d6e1d7;border-radius:8px;background:#fff;color:#385541;max-width:100%}
.mistake-workspace button{font:inherit;font-size:13px;padding:10px 14px;background:#185d49;border:1px solid #185d49;border-radius:9px;color:#fff;cursor:pointer}
.mistake-workspace .secondary{color:#40654d;background:#fff;border-color:#d2dfd5}
.mistake-workspace .text-button{padding:5px;background:transparent;color:#5b7d64;border:0}
.mistake-workspace button:disabled{opacity:.45;cursor:not-allowed}
.card-top{display:flex;justify-content:space-between;align-items:center;gap:12px}
.subject-pill,.status-pill{font-size:11px;border-radius:6px;padding:5px 10px;background:#edf3ec;color:#5e7c62}
.status-pill{background:#faf4e3;color:#8e7745}
.source-label{font-size:12px;color:#849285;margin:12px 0 7px}
.mistake-card h2{font-size:18px;line-height:1.7;margin:0 0 10px}
.options{font-size:14px;line-height:1.8}
.knowledge-chips{display:flex;flex-wrap:wrap;gap:7px}
.knowledge-chips span{font-size:11px;padding:5px 9px;background:#f2f6ef;border-radius:5px;color:#6e836b}
.own-answer{font-size:14px;line-height:1.8;padding:10px;background:#f6f8f3;border-radius:7px;margin:10px 0 5px}
.actions{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin:10px 0}
.correction-field{display:grid;gap:8px;font-size:13px;color:#5b765f;margin-top:14px}
.correction-field textarea{width:100%;resize:vertical;line-height:1.8}
.review-choice{display:flex;align-items:center;gap:9px;font-size:12px;color:#69816a;margin-top:20px}
.review-choice input{accent-color:#185d49;width:16px;height:16px}
.evidence{display:block;max-width:100%;max-height:500px;object-fit:contain;margin:15px 0}
.history{padding-top:16px;margin-top:16px;border-top:1px solid #e2e9df}
.history article{font-size:13px;padding:12px 0;border-bottom:1px solid #edf1e9;line-height:1.7}
.history small{color:#849280}
.count-line{display:flex;align-items:center;justify-content:space-between;font-size:13px;color:#6f846f;padding:12px 0;border-bottom:1px solid #e9eee6}
.count-line strong{font-size:25px;font-weight:500;color:#365c3f}
.review-button{width:100%;margin-top:10px}
.small-note{font-size:11px;line-height:1.8;color:#8a9987;margin-bottom:0}
.notice{font-size:13px;line-height:1.8;padding:14px;border-radius:8px;margin:0 0 18px}
.error{background:#fff0ec;color:#a24a3b}
.success{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;background:#eaf3e8;color:#497543}
.empty{font-size:13px;text-align:center;color:#84947e;padding:40px 10px}
.review-dialog{width:min(680px,94vw);max-height:90dvh;box-sizing:border-box;border:1px solid #d0dfce;border-radius:15px;padding:24px;color:#36553c}
.review-dialog::backdrop{background:rgb(22 40 25 / 60%)}
.review-dialog li{border-top:1px solid #e3eadf;padding:16px 5px;font-size:14px;line-height:1.8}
.review-dialog li>span,.review-dialog li>small{font-size:12px;color:#83917c}
@container(max-width:650px){.page-header{align-items:start;flex-direction:column;gap:12px}
.page-header h1{font-size:26px}
.header-controls{width:100%}
.panel{padding:17px}
.filters{flex-direction:column}
.card-top{align-items:start}
.actions button{flex:1}
}

</style>
