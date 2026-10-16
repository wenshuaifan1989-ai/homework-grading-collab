<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useHomeworkStore } from '@/stores/homework'

const emit = defineEmits<{
  upload: [file: File, subject: string, grade: string, model: string]
  analyze: [file: File, subject: string, grade: string, model: string]
}>()

const homework = useHomeworkStore()

const file = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const previewUrl = ref('')
const subject = ref('math')
const grade = ref('grade8')
const model = ref('')
const dragOver = ref(false)
const mode = ref<'ocr_llm' | 'llm_only'>('ocr_llm')

const subjects = [
  { value: 'math', label: '数学' },
  { value: 'chinese', label: '语文' },
  { value: 'english', label: '英语' },
  { value: 'physics', label: '物理' },
  { value: 'chemistry', label: '化学' },
]

const grades = [
  { value: 'grade1', label: '一年级' },
  { value: 'grade2', label: '二年级' },
  { value: 'grade3', label: '三年级' },
  { value: 'grade4', label: '四年级' },
  { value: 'grade5', label: '五年级' },
  { value: 'grade6', label: '六年级' },
  { value: 'grade7', label: '七年级' },
  { value: 'grade8', label: '八年级' },
  { value: 'grade9', label: '九年级' },
]

const availableModels = computed(() => {
  return homework.models.filter((m: any) => m.enabled)
})

const textModels = computed(() => {
  return homework.models.filter((m: any) => m.enabled && (m.type === 'text' || m.supported_features?.includes('text')))
})

const visionModels = computed(() => {
  return homework.models.filter((m: any) => m.enabled && (m.type === 'vision' || m.supported_features?.includes('vision')))
})

watch(mode, () => {
  model.value = ''
})

function handleFile(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (f) setFile(f)
}

function setFile(f: File) {
  if (!f.type.startsWith('image/')) return
  file.value = f
  previewUrl.value = URL.createObjectURL(f)
}

function handleDrop(e: DragEvent) {
  dragOver.value = false
  const f = e.dataTransfer?.files?.[0]
  if (f) setFile(f)
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    fileInput.value?.click()
  }
}

function resetFile() {
  file.value = null
  previewUrl.value = ''
  model.value = ''
  if (fileInput.value) fileInput.value.value = ''
}

function submit() {
  if (!file.value) return
  if (mode.value === 'ocr_llm') {
    emit('upload', file.value, subject.value, grade.value, model.value || '')
  } else {
    emit('analyze', file.value, subject.value, grade.value, model.value || '')
  }
  resetFile()
}
</script>

<template>
  <div class="card">
    <div class="card-header">上传作业</div>

    <div
      class="upload-zone"
      :class="{ 'drag-over': dragOver }"
      role="button"
      tabindex="0"
      :aria-label="file ? '点击更换图片' : '点击或拖拽上传作业图片'"
      @click="fileInput?.click()"
      @keydown="handleKeydown"
      @dragover.prevent="dragOver = true"
      @dragleave="dragOver = false"
      @drop.prevent="handleDrop"
    >
      <template v-if="!file">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="17 8 12 3 7 8"/>
          <line x1="12" y1="3" x2="12" y2="15"/>
        </svg>
        <p>点击或拖拽上传作业图片</p>
        <p style="font-size:0.75rem;margin-top:4px;">支持 JPG / PNG，最大 10MB</p>
      </template>
      <img v-else :src="previewUrl" class="preview-img" alt="作业图片预览" />
      <input
        ref="fileInput"
        type="file"
        accept="image/jpeg,image/png,image/webp"
        hidden
        aria-label="选择作业图片文件"
        @change="handleFile"
      />
    </div>

    <div style="display:flex;gap:14px;margin-top:18px;align-items:flex-end;flex-wrap:wrap;">
      <div class="form-group" style="flex:1;min-width:120px;margin-bottom:0;">
        <label class="form-label" for="upload-subject">科目</label>
        <select id="upload-subject" v-model="subject" class="form-select">
          <option v-for="s in subjects" :key="s.value" :value="s.value">{{ s.label }}</option>
        </select>
      </div>
      <div class="form-group" style="flex:1;min-width:120px;margin-bottom:0;">
        <label class="form-label" for="upload-grade">年级</label>
        <select id="upload-grade" v-model="grade" class="form-select">
          <option v-for="g in grades" :key="g.value" :value="g.value">{{ g.label }}</option>
        </select>
      </div>
      <div class="form-group" style="flex:1;min-width:140px;margin-bottom:0;">
        <label class="form-label" for="upload-mode">处理模式</label>
        <select id="upload-mode" v-model="mode" class="form-select">
          <option value="ocr_llm">阿里云OCR+大模型批改</option>
          <option value="llm_only">大模型分析</option>
        </select>
      </div>
      <div class="form-group" style="flex:1;min-width:140px;margin-bottom:0;" v-if="availableModels.length > 0">
        <label class="form-label" for="upload-model">选择模型</label>
        <select id="upload-model" v-model="model" class="form-select">
          <option value="" disabled>选择模型</option>
          <option v-for="m in availableModels" :key="m.name" :value="m.name">{{ m.name }} ({{ m.type === 'text' ? '文本' : '视觉' }})</option>
        </select>
      </div>
      <button
        class="btn btn-primary"
        :disabled="!file"
        aria-label="提交"
        @click="submit"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:16px;height:16px;" aria-hidden="true">
          <polyline points="20 6 9 17 4 12"/>
        </svg>
        {{ mode === 'ocr_llm' ? '提交批改' : '分析题目' }}
      </button>
    </div>
  </div>
</template>
