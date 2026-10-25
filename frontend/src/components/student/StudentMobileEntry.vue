<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { studentExperience } from '@/student/experience'
import { createMobileEntrySession, type MobileEntryState } from '@/student/mobileEntry'

const props = defineProps<{ studentId: number }>()
const emit = defineEmits<{ close: [] }>()
const dialog = ref<HTMLDialogElement | null>(null)
const state = ref<MobileEntryState>({ phase: 'loading', link: null, busy: false, error: '' })
const copied = ref(false)
const canCopy = computed(() => typeof navigator !== 'undefined' && !!navigator.clipboard?.writeText)
let session: ReturnType<typeof createMobileEntrySession> | null = null
let mounted = false, closed = false, copyGeneration = 0

function restart() {
  session?.stop()
  copyGeneration++; copied.value = false
  state.value = { phase: 'loading', link: null, busy: false, error: '' }
  session = createMobileEntrySession(studentExperience.mobileEntry, props.studentId,
    next => { if (mounted && !closed) state.value = next })
  void session.start()
}
function close() {
  if (closed) return
  closed = true; copyGeneration++
  session?.stop(); dialog.value?.close(); emit('close')
}
function retry() { if (!closed) void session?.start() }
async function copyLink() {
  if (closed || !state.value.link || !navigator.clipboard?.writeText) return
  const request = ++copyGeneration, id = props.studentId, url = state.value.link.phone_url
  try {
    await navigator.clipboard.writeText(url)
    if (mounted && !closed && request === copyGeneration && id === props.studentId && state.value.link?.phone_url === url) copied.value = true
  } catch { if (mounted && !closed && request === copyGeneration) copied.value = false }
}
watch(() => props.studentId, () => { if (mounted && !closed) restart() })
onMounted(async () => {
  mounted = true
  await nextTick()
  if (!mounted || closed) return
  dialog.value?.showModal()
  restart()
})
onBeforeUnmount(() => {
  mounted = false; closed = true; copyGeneration++
  session?.stop(); dialog.value?.close()
})
</script>

<template>
  <dialog ref="dialog" class="mobile-entry" aria-labelledby="mobile-entry-title" @cancel.prevent="close">
    <header><h2 id="mobile-entry-title">手机端入口</h2><button type="button" class="close" aria-label="关闭手机端入口" @click="close">×</button></header>
    <p class="intro">扫码打开完整手机版，拍照和提交在手机网页里完成。</p>
    <p v-if="state.phase==='loading'" role="status">正在读取手机端入口…</p>
    <template v-if="state.link">
      <img class="qr" :src="state.link.qr_image" alt="扫描二维码，打开手机端网页" width="240" height="240" />
      <p class="muted">沿用同一个手机地址，可反复扫描此二维码。</p>
      <p class="muted">本地预览：手机与电脑连接同一 Wi-Fi。</p>
      <details><summary>查看手机地址</summary><p class="link-text">{{ state.link.phone_url }}</p><button v-if="canCopy" type="button" class="secondary" @click="copyLink">{{ copied ? '已复制链接' : '复制手机地址' }}</button><p v-else class="muted">可选中上方地址，复制到手机浏览器打开。</p></details>
    </template>
    <p v-if="state.error" class="error" role="alert">{{ state.error }}</p>
    <footer><button v-if="state.phase==='error'" type="button" class="secondary" :disabled="state.busy" @click="retry">重新读取入口</button><button type="button" @click="close">关闭</button></footer>
  </dialog>
</template>

<style scoped>
.mobile-entry{margin:auto;width:min(460px,calc(100vw - 32px));max-height:calc(100dvh - 40px);box-sizing:border-box;overflow:auto;padding:24px;border:1px solid #dce7df;border-radius:18px;background:#fff;color:#284b3b;box-shadow:0 24px 72px #183f4930}.mobile-entry::backdrop{background:#19352e70}header{display:flex;align-items:center;justify-content:space-between;gap:14px}h2{margin:0;font-size:22px}.intro{font-size:14px;line-height:1.8;margin:16px 0 20px}.qr{display:block;max-width:100%;height:auto;margin:0 auto 18px;border:1px solid #e2e9e2;border-radius:10px}.muted{font-size:13px;color:#667c70;line-height:1.8}.link-text{font-size:12px;color:#526c5b;overflow-wrap:anywhere}details{font-size:13px;line-height:1.8}summary{cursor:pointer;min-height:44px;display:flex;align-items:center}.error{font-size:14px;line-height:1.8;color:#a33131}button{min-height:44px;border:0;border-radius:8px;padding:10px 16px;background:#185d49;color:#fff;font:inherit;cursor:pointer}.close{min-width:44px;padding:0;background:transparent;color:#526c5b;font-size:28px}.secondary{background:#edf3ee;color:#285c43;font-size:13px}button:disabled{opacity:.6;cursor:wait}button:focus-visible,summary:focus-visible{outline:3px solid #9ec7b6;outline-offset:3px}footer{display:flex;justify-content:flex-end;gap:10px;margin-top:20px}@media(max-width:580px){.mobile-entry{width:calc(100vw - 20px);padding:18px;max-height:calc(100dvh - 20px);padding-bottom:max(18px,env(safe-area-inset-bottom))}}
</style>
