import { defineStore } from 'pinia'
import { ref } from 'vue'
import { homeworkApi, type TaskStatusResponse, type GradingResultResponse, type ModelInfo, type TaskItem } from '@/api/homework'

export const useHomeworkStore = defineStore('homework', () => {
  const tasks = ref<TaskItem[]>([])
  const currentResult = ref<GradingResultResponse | null>(null)
  const loading = ref(false)
  const error = ref('')
  const models = ref<ModelInfo[]>([])
  const selectedModel = ref<string>('')

  async function fetchTasks(page: number = 1, pageSize: number = 20) {
    error.value = ''
    try {
      const { data } = await homeworkApi.getTaskList(page, pageSize)
      tasks.value = data.data.items
    } catch (e) {
      error.value = '获取任务列表失败，请稍后重试'
      console.error(e)
    }
  }

  async function fetchModels() {
    try {
      const { data } = await homeworkApi.getModels()
      models.value = data.data.models || []
      const defaultModel = models.value.find(m => m.enabled && (m.type === 'text' || m.supported_features?.includes('text')))
      if (defaultModel) {
        selectedModel.value = defaultModel.name
      }
    } catch (e) {
      console.error('获取模型列表失败:', e)
      models.value = []
    }
  }

  async function upload(file: File, subject: string, grade: string, model?: string) {
        const form = new FormData()
        form.append('file', file)
        form.append('subject', subject)
        form.append('grade', grade)
        if (model) {
            form.append('model', model)
        }
        const { data } = await homeworkApi.upload(form)
        const task: TaskItem = {
            task_id: data.data.task_id,
            status: 'PENDING',
            subject,
            accuracy: 0,
            created_at: new Date().toISOString(),
            questions: [],
            question_count: 0,
        }
        tasks.value.unshift(task)
        return data.data.task_id
    }

    async function analyze(file: File, subject: string, grade: string, model?: string) {
        const form = new FormData()
        form.append('file', file)
        form.append('subject', subject)
        form.append('grade', grade)
        if (model) {
            form.append('model', model)
        }
        const { data } = await homeworkApi.analyze(form)
        const task: TaskItem = {
            task_id: data.data.task_id,
            status: 'PENDING',
            subject,
            accuracy: 0,
            created_at: new Date().toISOString(),
            questions: [],
            question_count: 0,
        }
        tasks.value.unshift(task)
        return data.data.task_id
    }

  async function pollStatus(taskId: string): Promise<TaskStatusResponse> {
    const { data } = await homeworkApi.getStatus(taskId)
    const t = tasks.value.find((x) => x.task_id === taskId)
    if (t) {
      t.status = data.data.status
    }
    return data.data
  }

  async function fetchResult(taskId: string) {
    loading.value = true
    try {
      const { data } = await homeworkApi.getResult(taskId)
      currentResult.value = data.data
      const t = tasks.value.find((x) => x.task_id === taskId)
      if (t && currentResult.value) {
        t.status = 'SUCCESS'
        t.accuracy = currentResult.value.accuracy
      }
    } finally {
      loading.value = false
    }
  }

  return { 
    tasks, 
    currentResult, 
    loading, 
    error, 
    models,
    selectedModel,
    upload, 
    analyze,
    pollStatus, 
    fetchResult, 
    fetchTasks,
    fetchModels 
  }
})
