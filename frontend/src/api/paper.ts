import client from './client'

type Envelope<T> = { code: number; message: string; data: T }

export interface PaperQuestion {
  id: number
  subject: string
  grade: string
  question_text: string | null
  question_type: string | null
  options: string[] | Record<string, string> | null
  correct_answer: string | null
  analysis: string | null
  difficulty: string | null
  knowledge_points: string[]
  confidence: number | null
  review_status: string
  clean_image_status: string
  asset_version: string
}

export interface PaperGradingResult {
  id: number
  question_no: string
  result: string
  score: number
  max_score: number
  confidence: number | null
  error_type: string | null
  knowledge_points: string[]
  image_index: number | null
  question_text?: string | null
  question_type?: string | null
  student_answer?: string | null
  correct_answer?: string | null
  analysis?: string | null
}

export interface PaperSource {
  source_id: number
  asset_id: number
  source_task_id: string
  source_image_id: number
  page_index: number
  question_no: string | null
  bbox: { x1: number; y1: number; x2: number; y2: number }
  provider: string
  provider_version: string
  link_status: string
  review_status: string
  crop_url: string
  original_url: string
  question: PaperQuestion | null
  grading_result: PaperGradingResult | null
}

export interface MistakeItem {
  id: number
  student_id: number
  student_name?: string
  assignment_id: number
  assignment_title?: string
  subject?: string
  question_no?: string
  knowledge_points: string[]
  question: PaperQuestion | null
  grading_result: PaperGradingResult | null
  source_task_id: string
  source_id?: number | null
  source_page_index: number | null
  source_bbox: PaperSource['bbox'] | null
  crop_url: string
  original_url: string
  status: string
  detection_basis: string
  created_at: string
}

async function getData<T>(path: string, params?: Record<string, unknown>): Promise<T> {
  const response = await client.get<Envelope<T>>(path, { params })
  return response.data.data
}

async function postData<T>(path: string, body?: unknown): Promise<T> {
  const response = await client.post<Envelope<T>>(path, body)
  return response.data.data
}

async function patchData<T>(path: string, body?: unknown): Promise<T> {
  const response = await client.patch<Envelope<T>>(path, body)
  return response.data.data
}

export const paperApi = {
  digitizeTask(taskId: string) {
    return postData<{
      task_id: string
      provider: string
      provider_version: string
      runs: Array<{ page_index: number; status: string; candidate_count: number; failure_reason?: string | null }>
      sources: PaperSource[]
      accuracy_status: string
    }>(`/paper/tasks/${encodeURIComponent(taskId)}/digitize`)
  },
  taskAssets(taskId: string) {
    return getData<{
      task_id: string
      status: string
      sources: PaperSource[]
      grading_results: PaperGradingResult[]
      accuracy_status: string
    }>(`/paper/tasks/${encodeURIComponent(taskId)}/assets`)
  },
  reviewSource(sourceId: number, body: Record<string, unknown>) {
    return patchData<{
      source: PaperSource
      mistake_created: boolean
      mistake_id: number | null
      mistake_status_reason: string | null
      clean_image_status: string
    }>(`/paper/sources/${sourceId}/review`, body)
  },
  classMistakes(classId: number, studentId?: number) {
    return getData<{ class_id: number; items: MistakeItem[] }>(
      `/paper/classes/${classId}/mistakes`, studentId ? { student_id: studentId } : undefined,
    )
  },
  studentMistakes(studentId: number, filters?: { subject?: string; knowledge_point?: string }) {
    return getData<{ student_id: number; items: MistakeItem[] }>(
      `/paper/students/${studentId}/mistakes`, filters,
    )
  },
  submitCorrection(mistakeId: number, answer: string, note?: string) {
    return postData<{ attempt_id: number; mistake_id: number; status: string }>(
      `/paper/mistakes/${mistakeId}/corrections`, { answer, note },
    )
  },
  markMastered(mistakeId: number, note?: string) {
    return postData<{ attempt_id: number; mistake_id: number; status: string }>(
      `/paper/mistakes/${mistakeId}/mastery`, { note },
    )
  },
  correctionHistory(mistakeId: number) {
    return getData<{ mistake_id: number; items: Array<Record<string, any>> }>(
      `/paper/mistakes/${mistakeId}/history`,
    )
  },
  reviewCorrection(mistakeId: number, attemptId: number, accepted: boolean, feedback?: string) {
    return postData<{ attempt_id: number; mistake_id: number; status: string }>(
      `/paper/mistakes/${mistakeId}/corrections/${attemptId}/review`, { accepted, feedback },
    )
  },
  async image(path: string, kind: 'crop' | 'original'): Promise<Blob> {
    const endpoint = path.split('?')[0].replace(/^\/api\/v1/, '')
    const response = await client.get<Blob>(endpoint, {
      params: { kind },
      responseType: 'blob',
    })
    return response.data
  },
}
