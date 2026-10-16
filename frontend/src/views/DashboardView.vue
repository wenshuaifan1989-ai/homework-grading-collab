<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useHomeworkStore } from '@/stores/homework'
import UploadForm from '@/components/UploadForm.vue'
import TaskList from '@/components/TaskList.vue'

const homework = useHomeworkStore()
const polling = ref<ReturnType<typeof setInterval> | null>(null)

onMounted(() => {
  homework.fetchTasks()
  homework.fetchModels()
  
  polling.value = setInterval(() => {
    homework.tasks
      .filter((t) => !['SUCCESS', 'FAILED'].includes(t.status))
      .forEach((t) => homework.pollStatus(t.task_id))
  }, 10000)
})

onUnmounted(() => {
  if (polling.value) clearInterval(polling.value)
})

async function handleUpload(file: File, subject: string, grade: string, model: string) {
  await homework.upload(file, subject, grade, model)
}

async function handleAnalyze(file: File, subject: string, grade: string, model: string) {
  await homework.analyze(file, subject, grade, model)
}
</script>

<template>
  <div>
    <div class="page-header">
      <h1>作业批改</h1>
      <p>上传作业图片，AI 自动识别并批改</p>
    </div>

    <UploadForm @upload="handleUpload" @analyze="handleAnalyze" />

    <div style="margin-top:24px;">
      <TaskList :tasks="homework.tasks" />
    </div>
  </div>
</template>
