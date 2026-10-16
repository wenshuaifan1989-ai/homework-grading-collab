import client from './client'

export interface TaskStatusResponse {
  task_id: string
  status: string
  created_at: string
  updated_at: string
  failure_code?: string | null
  failure_message?: string | null
  call_id?: string | null
  can_retry?: boolean
}

export interface GradingResultItem {
  question_block_id: number
  question_no: string
  question_text: string
  student_answer: string
  score: number
  max_score: number
  result: string
  comment?: string
  analysis?: string
  confidence: number
}

export interface GradingResultResponse {
  task_id: string
  subject: string
  grade: string
  total_score: number
  total_max_score: number
  accuracy: number
  created_at: string
  results: GradingResultItem[]
  total_accuracy: number | null // API contract: percentage 0-100, including zero
}

export interface QuestionSummary {
  question_no: string
  question_text: string
  accuracy: number
  result: string
}

export interface TaskItem {
  task_id: string
  subject: string
  status: string
  accuracy: number
  created_at: string
  questions: QuestionSummary[]
  question_count: number
}

export interface ModelInfo {
  name: string
  provider: string
  type: string
  model_id: string
  enabled: boolean
  supported_features?: string[]
}

export interface TaskListResponse {
  items: TaskItem[]
  total: number
  page: number
  page_size: number
}

export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export const homeworkApi = {
  upload(formData: FormData) {
    return client.post<ApiResponse<{ task_id: string }>>('/homework/upload', formData)
  },
  getStatus(taskId: string) {
    return client.get<ApiResponse<TaskStatusResponse>>(`/homework/status/${taskId}`)
  },
  retryTask(taskId: string) {
    return client.post<ApiResponse<{ task_id: string; status: string; queued: boolean }>>(
      `/homework/retry/${encodeURIComponent(taskId)}`,
      { confirm_possible_duplicate_charge: true },
    )
  },
  getResult(taskId: string) {
    return client.get<ApiResponse<GradingResultResponse>>(`/homework/result/${taskId}`)
  },
  getTaskList(page: number = 1, pageSize: number = 20) {
    return client.get<ApiResponse<TaskListResponse>>(`/homework/list?page=${page}&page_size=${pageSize}`)
  },
  getModels() {
    return client.get<ApiResponse<{ models: ModelInfo[] }>>('/models')
  },
  analyze(formData: FormData) {
    return client.post<ApiResponse<{ task_id: string }>>('/homework/analyze', formData)
  },
}
