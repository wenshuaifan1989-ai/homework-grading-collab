import client from './client'

type Envelope<T> = { code: number; message: string; data: T }
export type PlanLevel = 'L1' | 'L2' | 'L3'

export interface QuestionBankItem {
  id: number
  subject: string
  grade: string
  question_text: string
  question_type: string
  options?: string[] | Record<string, string> | null
  correct_answer: string
  analysis: string
  difficulty: 'easy' | 'medium' | 'hard'
  knowledge_points: string[]
  review_status: string
  rights_basis: string
  rights_reference: string
}

export interface PlanQuestion {
  source_asset_id: number
  max_score: number
}

export interface PlanRequest {
  idempotency_key: string
  class_id: number
  title: string
  description?: string
  subject: string
  grade: string
  assignment_date: string
  due_at?: string
  target_knowledge_points: string[]
  question_types: string[]
  question_count_per_tier: number
  difficulty: 'easy' | 'medium' | 'hard' | 'mixed'
  duration_minutes?: number
  tier_strategy: Record<PlanLevel, string>
  variants: Array<{ level: PlanLevel; questions: PlanQuestion[] }>
}

export interface AssignmentPlan {
  id: number
  idempotency_key: string
  class_id: number
  assignment_id: number | null
  title: string
  description: string | null
  subject: string
  grade: string
  assignment_date: string
  due_at: string | null
  target_knowledge_points: string[]
  question_types: string[]
  difficulty: 'easy' | 'medium' | 'hard' | 'mixed'
  duration_minutes: number | null
  tier_strategy: Record<PlanLevel, string>
  status: 'DRAFT' | 'CONFIRMED' | 'PUBLISHED'
  question_count_per_tier: number
  variants: Array<{
    level: PlanLevel
    questions: Array<QuestionBankItem & { source_asset_id: number; max_score: number }>
  }>
}

async function getData<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  const response = await client.get<Envelope<T>>(url, { params })
  return response.data.data
}

async function postData<T>(url: string, body?: unknown, params?: Record<string, unknown>): Promise<T> {
  const response = await client.post<Envelope<T>>(url, body, { params })
  return response.data.data
}

async function putData<T>(url: string, body: unknown): Promise<T> {
  const response = await client.put<Envelope<T>>(url, body)
  return response.data.data
}

export const assignmentPlansApi = {
  aiStatus: () => getData<{ status: string; enabled: boolean; daily_request_limit: number; message: string }>(
    '/assignment-plans/ai-status',
  ),
  aiProposal: (body: { class_id: number; subject: string; grade: string; prompt: string }) =>
    postData<Record<string, unknown>>('/assignment-plans/ai-proposal', body),
  importLocal: (subject: string, grade: string) =>
    postData<{ created: number; reused: number; provider: string }>(
      '/assignment-plans/question-bank/import-local', undefined, { subject, grade },
    ),
  search: (classId: number, subject: string, grade: string, query: string, difficulty: string) =>
    getData<{ items: QuestionBankItem[] }>('/assignment-plans/question-bank/search', {
      class_id: classId, subject, grade, query, difficulty: difficulty || undefined,
    }),
  list: () => getData<AssignmentPlan[]>('/assignment-plans'),
  create: (body: PlanRequest) => postData<AssignmentPlan>('/assignment-plans', body),
  update: (id: number, body: PlanRequest) => putData<AssignmentPlan>(`/assignment-plans/${id}`, body),
  get: (id: number) => getData<AssignmentPlan>(`/assignment-plans/${id}`),
  confirm: (id: number) => postData<AssignmentPlan>(`/assignment-plans/${id}/confirm`),
  publish: (id: number) => postData<{ plan: AssignmentPlan; assignment_id: number; already_published: boolean }>(
    `/assignment-plans/${id}/publish`,
  ),
  async previewPdf(id: number, level: PlanLevel) {
    const response = await client.get<Blob>(
      `/assignment-plans/${id}/variants/${level}/print.pdf`, { responseType: 'blob' },
    )
    return response.data
  },
}
