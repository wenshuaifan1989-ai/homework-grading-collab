<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { createMistakePrintJob, prepareMistakePrint, type MistakePrintLayout, type MistakePrintSelection } from '@/student/mistakePrint'
import { subjectLabel } from '@/student/workbench'
import { useStudentHandheld } from '@/student/device'

const props = defineProps<{ studentId: number; subject: string; selection: MistakePrintSelection[] }>()
const emit = defineEmits<{ close: [] }>()
const dialog = ref<HTMLDialogElement | null>(null)
const handheld = useStudentHandheld()
const layout = ref<MistakePrintLayout>('split')
const prepared = computed(() => prepareMistakePrint(props.studentId, props.subject, props.selection))
const busy = ref(false)
const error = ref('')
const printNotice = ref('')
let mounted = false, closed = false, generation = 0
let job: ReturnType<typeof createMistakePrintJob> | null = null

function issueLabel(id: number): string {
  const item = props.selection.find(row => row.item.id === id)?.item
  if (!item) return id ? `题目 ${id}` : ''
  const assignment = item.assignment_title?.trim() || '作业名称待核对'
  return `${assignment} · ${item.question_no ? `原题号 ${item.question_no}` : `题目 ${id}`}`
}

function invalidate() {
  generation++
  job?.cancel()
  error.value = ''
  printNotice.value = ''
}
function close() {
  if (closed) return
  closed = true
  invalidate()
  job?.dispose()
  dialog.value?.close()
  emit('close')
}
async function print() {
  if (!mounted || closed || busy.value || !job || prepared.value.issues.length) return
  const request = ++generation
  error.value = ''
  printNotice.value = ''
  try {
    const result = await job.print(prepared.value, layout.value)
    if (mounted && !closed && request === generation && result === 'opened') printNotice.value = '已打开打印选择界面，可选择打印机或“另存为 PDF”。'
  } catch (failure) {
    if (mounted && !closed && request === generation) error.value = failure instanceof Error ? failure.message : '未能准备打印文档，请重试。'
  }
}
watch([() => props.studentId, () => props.subject, () => props.selection], invalidate, { deep: true })
watch(layout, invalidate)
onMounted(async () => {
  mounted = true
  await nextTick()
  if (!mounted || closed) return
  job = createMistakePrintJob(document, { onBusyChange: value => { if (mounted && !closed) busy.value = value } })
  dialog.value?.showModal()
})
onBeforeUnmount(() => {
  mounted = false
  generation++
  job?.dispose()
  dialog.value?.close()
})
</script>

<template>
  <dialog ref="dialog" class="mistake-print" :class="{ handheld }" aria-labelledby="mistake-print-title" @cancel.prevent="close">
    <header><div><p class="eyebrow">{{ subjectLabel(subject) }} · 已选 {{ selection.length }} 题</p><h2 id="mistake-print-title">下载 / 打印错题</h2></div><button type="button" class="close" aria-label="关闭错题打印窗口" @click="close">×</button></header>
    <template v-if="prepared.issues.length">
      <div class="issues" role="alert"><h3>以下题目暂不能打印</h3><p>请返回取消这些题目，或在资料补全后重试。本次不会遗漏题目直接生成。</p><ul><li v-for="(issue, index) in prepared.issues" :key="`${issue.id}-${index}`">{{ issue.id ? `${issueLabel(issue.id)}：` : '' }}{{ issue.message }}</li></ul></div>
    </template>
    <template v-else>
      <fieldset :disabled="busy" class="layouts"><legend>选择版式</legend><label :class="{ selected: layout === 'filled' }"><input v-model="layout" type="radio" value="filled" name="mistake-print-layout" /><span><strong>答案填充版</strong><small>每题下方附老师已公开的标准答案</small></span></label><label :class="{ selected: layout === 'split' }"><input v-model="layout" type="radio" value="split" name="mistake-print-layout" /><span><strong>试题答案拆分版</strong><small>先排无答案试题，答案另起一页</small></span></label></fieldset>
      <p class="notice">A4 纵向排版。下载时，请在打印窗口选择“另存为 PDF”。文档不含本人作答、解析及身份资料。</p>
      <p v-if="handheld" class="notice mobile-print-help">直接使用本机的打印选择界面，选择打印机或“另存为 PDF”。如果当前浏览器没有打印入口，请用手机系统浏览器打开本页。</p>
      <section class="preview" aria-label="错题文档内容预览"><h3>{{ subjectLabel(subject) }}错题练习</h3><article v-for="entry in prepared.entries" :key="entry.id" class="question"><p class="source">{{ entry.assignmentTitle }} · 原题号 {{ entry.questionNo }}</p><p class="stem">{{ entry.number }}. {{ entry.text }}</p><div v-if="entry.options.length" class="options"><p v-for="(option, index) in entry.options" :key="index">{{ option }}</p></div><img v-if="entry.imageDataUrl" :src="entry.imageDataUrl" :alt="`第 ${entry.number} 题题图`" /><template v-if="layout === 'filled'"><p class="answer-label">标准答案</p><p class="answer">{{ entry.answer }}</p></template><div v-else class="writing-space" aria-hidden="true"></div></article><section v-if="layout === 'split'" class="answers"><p class="page-break">打印时另起一页</p><h3>参考答案</h3><article v-for="entry in prepared.entries" :key="entry.id"><p class="source">{{ entry.number }}. {{ entry.assignmentTitle }} · 原题号 {{ entry.questionNo }}</p><p class="answer">{{ entry.answer }}</p></article></section></section>
    </template>
    <p v-if="busy" role="status" class="notice">正在准备或显示打印窗口，关闭打印窗口后可再次打印。</p>
    <p v-if="error" role="alert" class="error">{{ error }}</p><p v-if="printNotice" role="status" class="notice">{{ printNotice }}</p>
    <footer><button type="button" class="secondary" @click="close">返回选择题目</button><button v-if="!prepared.issues.length" type="button" :disabled="busy" @click="print">{{ busy ? '正在打开打印选择界面…' : handheld ? '在手机打印 / 存为 PDF' : '打印 / 另存为 PDF' }}</button></footer>
  </dialog>
</template>

<style scoped>
.mistake-print{margin:auto}
.mistake-print{width:min(820px,calc(100vw - 32px));max-height:calc(100dvh - 40px);box-sizing:border-box;overflow:auto;border:1px solid #dce7df;border-radius:18px;padding:24px;color:#284b3b;background:#fff;box-shadow:0 24px 72px #183f4930}.mistake-print::backdrop{background:#19352e70}header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}h2{font-size:22px;margin:0 0 14px}h3{font-size:17px}.eyebrow,.source{font-size:12px;color:#667e70;margin:0 0 8px}.close{background:transparent;color:#526c5b;padding:0;font-size:28px;min-width:40px}.layouts{border:0;padding:0;margin:12px 0;display:grid;grid-template-columns:1fr 1fr;gap:12px}.layouts legend{font-size:14px;font-weight:700;margin-bottom:10px}.layouts label{display:flex;align-items:flex-start;gap:10px;border:1px solid #dce6df;border-radius:10px;padding:14px;cursor:pointer}.layouts label.selected{border-color:#438c6e;background:#edf6ef}.layouts input{accent-color:#185d49;margin-top:4px}.layouts strong{display:block;font-size:14px}.layouts small{display:block;color:#637b6c;line-height:1.7;margin-top:5px;font-size:12px}.notice{font-size:13px;line-height:1.8;color:#5d7768}.preview{margin-top:16px;padding:24px;border:1px solid #dce6df;border-radius:10px;background:#fff;color:#24392d;max-height:52dvh;overflow:auto}.preview h3{margin:0 0 22px}.question{margin-bottom:28px}.stem,.answer,.options p{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.8;margin:0 0 8px}.question img{display:block;max-width:100%;max-height:360px;object-fit:contain;margin:12px 0}.options{margin:10px 0}.answer-label{font-size:13px;font-weight:700;margin:14px 0 5px}.answer{font-size:14px}.writing-space{height:60px}.answers{border-top:2px dashed #c7d8ca;margin-top:20px;padding-top:16px}.answers article{margin-bottom:24px}.page-break{font-size:12px;color:#778a7c;text-align:center;margin:0 0 20px}.issues{padding:14px 18px;background:#fff7e9;border-radius:10px;color:#7a5427;font-size:14px;line-height:1.8}.issues h3{margin:0 0 8px}.issues p{margin:0}.issues ul{padding-left:20px}.error{color:#a33131;line-height:1.8;font-size:14px}button{min-height:42px;border:0;border-radius:8px;padding:10px 16px;background:#185d49;color:#fff;font:inherit;cursor:pointer}button:disabled{opacity:.6;cursor:wait}.secondary{background:#edf3ee;color:#285c43}footer{position:sticky;bottom:-24px;background:#fff;display:flex;justify-content:flex-end;gap:10px;padding:18px 0 4px;margin-top:14px}
.mistake-print.handheld .preview{max-height:none;overflow:visible}
.mobile-print-help{padding:10px 12px;background:#edf6ef;border-radius:8px}
@media(max-width:700px){
  .mistake-print{width:calc(100vw - 16px);max-width:100%;max-height:calc(100dvh - 16px);padding:16px 12px;padding-bottom:max(16px,env(safe-area-inset-bottom));overscroll-behavior:contain}
  header>div{min-width:0;overflow-wrap:anywhere}h2{font-size:20px;line-height:1.5}
  button{min-height:44px;touch-action:manipulation}.close{min-width:44px;flex-shrink:0}
  .layouts{grid-template-columns:1fr}.layouts label{min-height:44px;box-sizing:border-box}
  .layouts input{min-width:20px;min-height:20px}.preview{padding:14px;max-height:none;overflow:visible}
  .source,.issues{overflow-wrap:anywhere}.issues{padding:12px}
  footer{bottom:-16px;flex-wrap:wrap;padding-bottom:max(12px,env(safe-area-inset-bottom))}
  footer button{flex:1 1 100%;white-space:normal;line-height:1.5}
}
</style>
