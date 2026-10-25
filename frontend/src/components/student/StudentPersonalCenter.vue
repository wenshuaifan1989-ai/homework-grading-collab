<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { LinkedStudent, StudentBinding } from '@/api/student'
import { maskedPhone, profileBinding, relationshipLabel, relationshipTypeLabel } from '@/student/profile'
import { studentExperience, type StudentIdentityDetails, type StudentRelative } from '@/student/experience'
const props = defineProps<{ account: { phone?: string | null } | null; student?: LinkedStudent; binding: StudentBinding | null }>()
const details = ref<StudentIdentityDetails | null>(null)
const relatives = ref<StudentRelative[] | null>(null)
const loading = ref(false)
const identityError = ref('')
const familyError = ref('')
let serial = 0
const verified = computed(() => profileBinding(props.student, props.binding, 'ready'))
const classrooms = computed(() => (props.student?.classes || []).filter(item => item.status === 'active'))
const className = computed(() => details.value?.class_name || verified.value.className || classrooms.value.map(item => item.class_name).join(' / ') || '待核对')
async function reload() {
  const request = ++serial, id = props.student?.student_id
  details.value = null; relatives.value = null; identityError.value = ''; familyError.value = ''
  if (!id) { loading.value = false; return }
  loading.value = true
  await Promise.all([
    (async () => {
      if (!studentExperience.identity) return
      try {
        const data = await studentExperience.identity(id)
        if (request !== serial) return
        if (data.student_id !== id || !classrooms.value.some(item => item.class_id === data.class_id))
          throw Error('身份资料不一致，请联系老师核对。')
        if (props.binding?.is_bound && props.binding.student_id === id &&
            props.binding.class_id === data.class_id && props.binding.student_no &&
            data.student_no && props.binding.student_no !== data.student_no)
          throw Error('学号与已核对的绑定资料不一致。')
        details.value = data
      } catch { if (request === serial) identityError.value = '身份补充资料读取失败，请重试。' }
    })(),
    (async () => {
      if (!studentExperience.relatives) return
      try {
        const data = await studentExperience.relatives(id)
        if (request === serial) relatives.value = data
      } catch { if (request === serial) familyError.value = '家庭关联资料读取失败，请重试。' }
    })(),
  ])
  if (request === serial) loading.value = false
}
watch(() => props.student?.student_id, reload, { immediate: true })
onBeforeUnmount(() => { serial++ })
</script>
<template>
  <div class="personal-center">
    <section class="identity-panel" aria-labelledby="identity-heading">
      <p class="eyebrow">一个账号 · 一个孩子</p>
      <h2 id="identity-heading">身份资料</h2>
      <p class="muted">家人绑定同一个孩子后，查看同一份作业与错题。</p>
      <p v-if="!student" role="status">尚未确认唯一的学生绑定，请联系老师核对。</p>
      <dl v-else class="identity-grid">
        <div><dt>学校</dt><dd>{{ details?.school_name || '学校资料待提供' }}</dd></div>
        <div><dt>所属班级</dt><dd>{{ className }}</dd></div>
        <div><dt>学号</dt><dd>{{ details?.student_no || verified.studentNo || '学号待提供' }}</dd></div>
        <div><dt>学生序号</dt><dd>{{ details?.student_sequence || '学生序号待提供' }}</dd></div>
        <div><dt>当前账号手机号</dt><dd>{{ maskedPhone(account?.phone) }}</dd></div>
        <div><dt>与孩子的关系</dt><dd>{{ relationshipLabel(student) }}</dd></div>
      </dl>
      <p class="muted">学校、班级与学号共同确定学生身份。学生序号由老师单独分配，与学号不同。</p>
      <p v-if="identityError" class="error" role="alert">{{ identityError }}</p>
    </section>
    <section class="identity-panel" aria-labelledby="family-heading">
      <h2 id="family-heading">家庭关联</h2>
      <p class="muted">家人的身份关系用于说明与孩子的关系，不切换孩子的学习身份。</p>
      <p v-if="loading" role="status">正在读取关联资料…</p>
      <p v-else-if="familyError" class="error" role="alert">{{ familyError }}</p>
      <template v-else-if="relatives">
        <ul v-if="relatives.length" class="relatives">
          <li v-for="(relative,index) in relatives" :key="index">
            <strong>{{ relationshipTypeLabel(relative.relationship_type) }}</strong>
            <span>{{ relative.masked_phone && /^\d{3}\*{4}\d{4}$/.test(relative.masked_phone) ? relative.masked_phone : maskedPhone(relative.masked_phone) }}</span>
            <small v-if="relative.is_current">当前账号</small>
          </li>
        </ul>
        <p v-else class="muted">服务端尚未返回关联亲属。</p>
      </template>
      <p v-else class="muted">家庭成员列表尚未接通，当前只能确认本账号与孩子的关联关系。</p>
      <slot name="family-actions" />
      <button v-if="identityError || familyError" type="button" :disabled="loading" @click="reload">重新读取资料</button>
    </section>
  </div>
</template>
<style scoped>
.personal-center{display:grid;gap:20px;min-width:0}.identity-panel{background:#fff;border:1px solid #dfe8e2;border-radius:14px;padding:24px}
h2{font-size:20px;margin:0 0 14px;color:#254d3d}.eyebrow{font-size:12px;color:#567d67;margin:0 0 10px}.muted{font-size:13px;color:#667c70;line-height:1.8}
.identity-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 24px}.identity-grid div{padding:16px 0;border-bottom:1px solid #edf1ed;min-width:0}
dt{font-size:12px;color:#768579;margin-bottom:8px}dd{margin:0;color:#284b3b;font-weight:600;overflow-wrap:anywhere}
.relatives{list-style:none;padding:0}.relatives li{display:flex;flex-wrap:wrap;gap:16px;padding:16px 0;border-bottom:1px solid #edf1ed;color:#456351}
small{padding:2px 8px;border-radius:8px;background:#e2f0e7}.error{color:#a33131}button{min-height:40px;background:#185d49;color:white;border:0;border-radius:8px;padding:8px 14px}
@media(max-width:580px){.identity-panel{padding:18px}.identity-grid{grid-template-columns:1fr}}
@media(pointer:coarse),(max-width:700px){button{min-height:44px;font:inherit;font-size:14px}.identity-panel{overflow-wrap:anywhere}.relatives li{gap:10px 16px}}
</style>
