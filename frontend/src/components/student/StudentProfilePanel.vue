<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { User } from '@/api/auth'
import { studentApi, type LinkedStudent, type StudentBinding } from '@/api/student'
import { maskedEmail, maskedPhone, profileBinding, relationshipLabel, type ProfileBindingState, type ProfileMetric } from '@/student/profile'

const props = defineProps<{ account: User | null; student?: LinkedStudent | null; metrics: ProfileMetric[]; disabled?: boolean }>()
const dialog = ref<HTMLDialogElement | null>(null)
const tab = ref('overview')
const tabs = [{ key: 'overview', label: '资料概览' }, { key: 'classroom', label: '班级身份' }, { key: 'family', label: '家庭关联' }, { key: 'help', label: '使用帮助' }]
const binding = ref<StudentBinding | null>(null)
const bindingState = ref<ProfileBindingState>('idle')
const identity = computed(() => profileBinding(props.student, binding.value, bindingState.value))
const classes = computed(() => (props.student?.classes || []).filter(item => item.status === 'active'))
let requestSerial = 0
async function loadBinding() {
  const request = ++requestSerial
  const studentId = props.student?.student_id
  const accountId = props.account?.id
  binding.value = null
  if (!props.student || props.account?.role !== 'student') {
    bindingState.value = 'not_applicable'
    return
  }
  bindingState.value = 'loading'
  try {
    const response = await studentApi.getBinding()
    if (request !== requestSerial || studentId !== props.student?.student_id || accountId !== props.account?.id) return
    binding.value = response.data.data
    bindingState.value = 'ready'
  } catch {
    if (request === requestSerial && studentId === props.student?.student_id && accountId === props.account?.id) bindingState.value = 'error'
  }
}
function openProfile() {
  if (props.disabled) return
  tab.value = 'overview'
  dialog.value?.showModal()
  void loadBinding()
}
function closed() { if (dialog.value?.open) return; requestSerial++; binding.value = null; bindingState.value = 'idle' }
function closeProfile() { dialog.value?.close(); closed() }
watch(() => [props.student?.student_id, props.account?.id], () => { if (dialog.value?.open) void loadBinding() })
onBeforeUnmount(() => { requestSerial++; dialog.value?.close() })
</script>
<template>
  <div class="student-profile-entry">
    <button type="button" class="profile-trigger" :disabled="disabled" @click="openProfile">个人信息</button>
    <dialog ref="dialog" class="profile-dialog" aria-labelledby="student-profile-title" @close="closed">
      <header class="profile-header">
        <div><p class="profile-eyebrow">我的学习资料</p><h2 id="student-profile-title">个人信息</h2></div>
        <button type="button" class="profile-close" @click="closeProfile">关闭个人信息</button>
      </header>
      <section class="profile-person" aria-label="当前学习身份">
        <span class="profile-avatar" aria-hidden="true">学</span>
        <div><h3>{{ student ? (identity.studentNo ? `学号 ${identity.studentNo}` : '我的学习身份') : '尚未选择学习身份' }}</h3><p>{{ classes.map(item => item.class_name).join(' · ') || '请先选择学生身份或核对班级资料' }}</p></div>
        <span class="relationship-badge">{{ relationshipLabel(student) }}</span>
      </section>
      <nav class="profile-tabs" aria-label="个人信息分类">
        <button v-for="item in tabs" :key="item.key" type="button" :aria-pressed="tab===item.key" @click="tab=item.key">{{ item.label }}</button>
      </nav>
      <div class="profile-content" :class="{ overview: tab==='overview' }">
        <template v-if="tab==='overview'">
          <section class="profile-section" aria-labelledby="profile-identity-heading">
            <h3 id="profile-identity-heading">身份资料</h3><p class="profile-note">以学号和学生序号识别学习身份。</p>
            <dl class="profile-fields">
              <div><dt>学号</dt><dd>{{ identity.studentNo || '当前资料未提供可核对的学号' }}</dd></div>
              <div><dt>学生序号</dt><dd>待提供</dd></div>
              <div><dt>所属班级</dt><dd>{{ classes.map(item => item.class_name).join(' · ') || '当前资料未提供' }}</dd></div>
            </dl>
            <p class="profile-note">学生序号由老师分配，是与学号分开的固定编号。当前资料尚未提供。</p>
          </section>
          <section class="profile-section" aria-labelledby="profile-study-heading">
            <h3 id="profile-study-heading">学习概况</h3><p class="profile-note">当前身份在本页面已加载的学习记录。</p>
            <div v-if="student && metrics.length" class="profile-metrics">
              <div v-for="item in metrics" :key="item.label"><span>{{ item.label }}</span><p><strong>{{ item.value !== null && Number.isInteger(item.value) && item.value >= 0 ? item.value : '—' }}</strong><small>{{ item.unit }}</small></p></div>
            </div>
            <p v-else class="profile-note">选择学习身份后可查看概况。</p>
            <p class="profile-note">待老师复核的作业仍在处理中，复核前不显示分数。</p>
          </section>
          <section class="profile-section profile-contact-section" aria-labelledby="profile-account-heading">
            <h3 id="profile-account-heading">登录与联系方式</h3><p class="profile-note">联系方式属于当前登录账户。</p>
            <dl class="profile-fields">
              <div><dt>登录状态</dt><dd>{{ account ? '已登录' : '登录资料待确认' }}</dd></div>
              <div><dt>手机号（已脱敏）</dt><dd>{{ maskedPhone(account?.phone) }}</dd></div>
              <div><dt>邮箱（已脱敏）</dt><dd>{{ maskedEmail(account?.email) }}</dd></div>
            </dl>
          </section>
        </template>
        <section v-else-if="tab==='classroom'" class="profile-section" aria-labelledby="profile-class-heading">
          <h3 id="profile-class-heading">班级与编号</h3>
          <p class="profile-note" :role="bindingState==='error' ? 'alert' : 'status'">{{ identity.message }}</p>
          <button v-if="student && account?.role==='student' && bindingState!=='loading'" type="button" class="profile-text-button" @click="loadBinding">重新核对绑定资料</button>
          <dl class="profile-fields">
            <div><dt>学号</dt><dd>{{ identity.studentNo || '当前资料未提供可核对的学号' }}</dd></div>
            <div><dt>学生序号</dt><dd>待提供</dd></div>
            <div><dt>所属班级</dt><dd>{{ classes.map(item => item.class_name).join(' · ') || '当前资料未提供' }}</dd></div>
            <div v-if="identity.className"><dt>学号所属班级</dt><dd>{{ identity.className }}</dd></div>
          </dl>
          <h4>关联班级</h4><ul v-if="classes.length" class="class-list"><li v-for="item in classes" :key="item.class_id"><span>{{ item.class_name }}</span><small>在班</small></li></ul><p v-else class="profile-note">当前没有可展示的在班记录。</p>
          <p class="profile-note">学生序号是老师分配的独立固定编号，当前资料尚未提供。班级、学号或学生序号有误，请联系老师核对。</p>
        </section>
        <section v-else-if="tab==='family'" class="profile-section" aria-labelledby="profile-family-heading">
          <h3 id="profile-family-heading">家庭关联</h3><p class="profile-note">当前账户与所选学生的关系：{{ relationshipLabel(student) }}。</p>
          <slot name="family"><p class="profile-note">家庭关系可在“我的作业 → 个人信息 → 家庭关联”中管理。</p><router-link to="/student" class="profile-link" @click="closeProfile">前往我的作业</router-link></slot>
        </section>
        <section v-else class="profile-section profile-help" aria-labelledby="profile-help-heading">
          <h3 id="profile-help-heading">使用帮助</h3>
          <details open><summary>如何更正个人资料？</summary><p>班级、学号和学生序号由老师核对。学号与学生序号是两个独立编号；学生页面不展示姓名。登录账户的联系方式需要更正时，请联系管理员。</p></details>
          <details><summary>怎样提交整份作业？</summary><p>从指定作业进入拍照提交，连续添加1–9张照片，检查页码顺序后一次提交。保留任务回执，等待老师复核时无需重复提交。</p></details>
          <details><summary>订正和自评掌握有什么区别？</summary><p>订正提交后等待老师审核。自评掌握只记录本人的学习判断，老师审核结果会单独保留。</p></details>
          <p class="profile-note">共用设备使用完毕后，请通过系统菜单退出登录。</p>
        </section>
      </div>
    </dialog>
  </div>
</template>
<style scoped>
.student-profile-entry{font-size:13px;color:#294b3b}
.student-profile-entry button{font:inherit;cursor:pointer;border:1px solid #d3dfd7;border-radius:9px;padding:9px 13px;background:#fff;color:#365d49}
.student-profile-entry button:disabled{opacity:.45;cursor:not-allowed}
.student-profile-entry :is(button,a,summary):focus-visible{outline:3px solid #9ec7b6;outline-offset:2px}
.student-profile-entry .profile-trigger{background:#edf5ef;border-color:#cfdfd3;white-space:nowrap;font-weight:600}
.profile-dialog{width:min(820px,calc(100vw - 32px));max-height:90dvh;box-sizing:border-box;margin:auto;padding:24px;border:1px solid #d5e1d7;border-radius:16px;background:#f8fbf8;color:#294b3b;overflow:auto}
.profile-dialog::backdrop{background:rgb(19 35 26 / 65%)}
.profile-header{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:20px}
.profile-eyebrow{font-size:11px;letter-spacing:.08em;color:#718676;margin:0 0 7px}
.profile-header h2{font-size:24px;margin:0}
.student-profile-entry .profile-close{font-size:12px}
.profile-person{display:flex;align-items:center;gap:14px;padding:18px;background:#eaf3ec;border:1px solid #dce8df;border-radius:12px;flex-wrap:wrap}
.profile-avatar{display:grid;place-items:center;width:48px;height:48px;flex:none;border-radius:50%;background:#185d49;color:#fff;font-size:21px}
.profile-person h3{font-size:18px;margin:0 0 5px;overflow-wrap:anywhere}
.profile-person p{font-size:12px;line-height:1.7;color:#6b8172;margin:0;overflow-wrap:anywhere}
.relationship-badge{font-size:11px;background:#fff;color:#54715e;padding:5px 9px;border-radius:6px;margin-left:auto}
.profile-tabs{display:flex;flex-wrap:wrap;gap:10px;margin-top:20px;border-bottom:1px solid #dfe8e1}
.student-profile-entry .profile-tabs button{border:0;border-bottom:2px solid transparent;border-radius:0;background:transparent;padding:11px 3px;color:#6b8172}
.student-profile-entry .profile-tabs button[aria-pressed=true]{border-bottom-color:#185d49;color:#185d49;font-weight:600}
.profile-content{padding-top:18px;min-width:0}
.profile-section{padding:18px;background:#fff;border:1px solid #e0e8e1;border-radius:12px;margin-bottom:14px}
.profile-section:last-child{margin-bottom:0}
.profile-section h3{font-size:16px;margin:0 0 9px}
.profile-section h4{font-size:13px;margin:18px 0 8px}
.profile-note{font-size:12px;color:#728678;line-height:1.8;margin:7px 0;overflow-wrap:anywhere}
.profile-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:17px 24px;margin:16px 0 0}
.profile-fields dt{font-size:11px;color:#7a8c7e;margin-bottom:6px}
.profile-fields dd{font-size:14px;line-height:1.7;margin:0;overflow-wrap:anywhere}
.profile-metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin:14px 0}
.profile-metrics>div{padding:12px;border-radius:9px;background:#f3f8f3;border:1px solid #e0e9e1}
.profile-metrics span{font-size:12px;color:#6b8172}
.profile-metrics p{margin:9px 0 0;display:flex;align-items:baseline;gap:7px}
.profile-metrics strong{font-size:25px;font-weight:500}
.profile-metrics small{font-size:11px;color:#7a8c7e}
.class-list{list-style:none;padding:0;margin:0}
.class-list li{display:flex;justify-content:space-between;gap:12px;padding:11px 0;border-bottom:1px solid #edf1ed}
.class-list small{font-size:11px;color:#63806a}
.student-profile-entry .profile-text-button{padding:4px 0;border:0;background:transparent;color:#326b50;font-size:12px}
.profile-link{display:inline-block;color:#326b50;margin-top:10px;text-decoration:none}
.profile-help details{padding:12px 0;border-bottom:1px solid #e7ede7;line-height:1.8;font-size:13px}
.profile-help summary{cursor:pointer}
.profile-help details p{font-size:12px;color:#728678;margin:8px 0 0}
@media(min-width:700px){.profile-content.overview{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;align-items:start}.overview .profile-section{margin-bottom:0}.overview .profile-fields{grid-template-columns:minmax(0,1fr);gap:12px}.overview .profile-metrics{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.overview .profile-contact-section{grid-column:1/-1}.overview .profile-contact-section .profile-fields{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:600px){.profile-dialog{padding:17px}.profile-fields{grid-template-columns:minmax(0,1fr)}.profile-person{padding:14px}.relationship-badge{margin-left:0}.profile-tabs{gap:8px}.profile-section{padding:15px}}
</style>
