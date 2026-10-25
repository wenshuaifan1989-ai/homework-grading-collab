<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { StudentAssignment } from '@/api/student'
import { studentExperience } from '@/student/experience'
import { createPhonePrintSession, type PhonePrintState } from '@/student/phonePrint'

const props = defineProps<{ assignment: StudentAssignment; studentId: number }>()
const emit = defineEmits<{ close: [] }>()
const dialog = ref<HTMLDialogElement | null>(null)
const state = ref<PhonePrintState>({ phase: 'loading', link: null, busy: false, error: '' })
const copied = ref(false)
const copyError = ref(false)
const canCopy = computed(() => typeof navigator !== 'undefined' && !!navigator.clipboard?.writeText)
let session: ReturnType<typeof createPhonePrintSession> | null = null
let mounted = false, closed = false, copyGeneration = 0
function restart() {
  session?.stop()
  copyGeneration++
  copied.value = false
  copyError.value = false
  state.value = { phase: 'loading', link: null, busy: false, error: '' }
  session = createPhonePrintSession(studentExperience.phonePrint,
    { student_id: props.studentId, assignment_id: props.assignment.id },
    next => { state.value = next })
  void session.start()
}
function close() {
  if (closed) return
  closed = true
  copyGeneration++
  session?.stop()
  dialog.value?.close()
  emit('close')
}
function retry() { if (mounted && !closed) void session?.start() }
async function copyLink() {
  const link = state.value.link
  if (!mounted || closed || !link || !canCopy.value) return
  const request = ++copyGeneration
  copyError.value = false
  try {
    await navigator.clipboard.writeText(link.phone_url)
    if (mounted && !closed && request === copyGeneration) copied.value = true
  } catch {
    if (mounted && !closed && request === copyGeneration) { copied.value = false; copyError.value = true }
  }
}
// Replacing an assignment after a status refresh keeps the same QR. A different context restarts it.
watch([() => props.studentId, () => props.assignment.id], () => { if (mounted && !closed) restart() })
onMounted(async () => {
  mounted = true
  await nextTick()
  if (!mounted || closed) return
  dialog.value?.showModal()
  restart()
})
onBeforeUnmount(() => {
  mounted = false
  copyGeneration++
  session?.stop()
  dialog.value?.close()
})
</script>

<template>
  <dialog ref="dialog" class="phone-print" aria-labelledby="phone-print-title" @cancel.prevent="close">
    <header><div><p class="eyebrow">老师发布的试卷 · 手机打开原文件</p><h2 id="phone-print-title">手机扫码打印</h2></div><button type="button" class="close" aria-label="关闭打印二维码窗口" @click="close">×</button></header>
    <p class="assignment-title">{{ assignment.title }}</p>
    <p v-if="assignment.class_name" class="muted">{{ assignment.class_name }}</p>
    <p v-if="state.phase === 'loading'" role="status">正在准备当前作业的打印二维码…</p>
    <template v-if="state.link">
      <div class="qr"><img :src="state.link.qr_image" alt="用手机扫描，打开老师发布的当前作业试卷" width="240" height="240" /></div>
      <ol><li>安卓手机与电脑连接同一 Wi-Fi，扫描二维码。</li><li>在手机打开或下载老师发布的试卷原文件。</li><li>在文件阅读器或浏览器中选择“打印”，连接打印机后确认。</li></ol>
      <p class="notice">能否打印取决于手机的打印服务和打印机连接。找不到“打印”时，可先下载试卷，再用支持打印的阅读器打开。</p>
      <details><summary>无法扫码？查看手机打开地址</summary><p class="link-text">{{ state.link.phone_url }}</p><button v-if="canCopy" type="button" class="secondary" @click="copyLink">{{ copied ? '已复制链接' : '复制手机链接' }}</button><p v-else class="muted">可以长按或选中上方地址复制。</p><p v-if="copyError" class="muted" role="status">未能自动复制，请选中上方地址手动复制。</p></details>
    </template>
    <p v-if="state.error" class="error" role="alert">{{ state.error }}</p>
    <button v-if="state.phase === 'error'" type="button" class="secondary" :disabled="state.busy" @click="retry">重新生成打印二维码</button>
    <footer><button type="button" @click="close">返回试卷</button></footer>
  </dialog>
</template>

<style scoped>
.phone-print{width:min(520px,calc(100vw - 32px));max-height:calc(100dvh - 40px);box-sizing:border-box;overflow:auto;border:1px solid #dce7df;border-radius:18px;padding:24px;color:#284b3b;background:#fff;box-shadow:0 24px 72px #183f4930}.phone-print::backdrop{background:#19352e70}header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}h2{font-size:22px;margin:0 0 14px}.eyebrow{font-size:12px;color:#667e70;margin:0 0 8px}.close{background:transparent;color:#526c5b;padding:0;font-size:28px;min-width:40px}.assignment-title{font-size:17px;font-weight:700;margin:8px 0}.muted{font-size:13px;color:#667c70;line-height:1.7}.qr{display:flex;justify-content:center;margin:20px 0}.qr img{max-width:100%;height:auto;border:1px solid #e2e9e2;border-radius:10px}ol{font-size:14px;line-height:1.9;padding-left:23px}.notice{padding:12px;border-radius:8px;background:#edf6f0;color:#315e47;font-size:13px;line-height:1.8}.error{color:#a33131;font-size:14px;line-height:1.7}.link-text{overflow-wrap:anywhere;word-break:break-all;font-size:12px;color:#526c5b}details{font-size:13px;line-height:1.7}summary{cursor:pointer}button{min-height:42px;border:0;border-radius:8px;padding:10px 16px;background:#185d49;color:#fff;font:inherit;cursor:pointer}.secondary{background:#edf3ee;color:#285c43;font-size:13px}button:disabled{opacity:.6;cursor:wait}footer{margin-top:22px;display:flex;justify-content:flex-end}@media(max-width:580px){.phone-print{padding:20px;width:calc(100vw - 24px)}}
</style>
