import client from './client'

type Envelope<T> = { code: number; message: string; data: T }

export interface SubjectTierRow {
  roster_id: number
  student_id: number | null
  student_name: string
  student_no?: string | null
  level: 'L1' | 'L2' | 'L3' | null
  level_label: string
  updated_at?: string | null
}

export interface VariantQuestion {
  id?: number
  source_type?: 'MANUAL' | 'ASSET'
  source_asset_id?: number | null
  question_text: string
  options?: string[] | Record<string, string> | null
  correct_answer?: string | null
  analysis?: string | null
  max_score: number
}

export interface AssignmentVariant {
  id: number
  level: 'L1' | 'L2' | 'L3'
  level_label: string
  version: number
  questions: VariantQuestion[]
}

async function getData<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  const response = await client.get<Envelope<T>>(url, { params })
  return response.data.data
}

async function putData<T>(url: string, body: unknown): Promise<T> {
  const response = await client.put<Envelope<T>>(url, body)
  return response.data.data
}

export const learningApi = {
  listTiers(classId: number, subject: string) {
    return getData<{ class_id: number; subject: string; students: SubjectTierRow[] }>(
      `/learning/classes/${classId}/tiers`, { subject },
    )
  },
  saveTiers(classId: number, subject: string, entries: Array<{ student_id: number; level: 'L1' | 'L2' | 'L3' }>) {
    return putData<{ changed_count: number; students: SubjectTierRow[] }>(
      `/learning/classes/${classId}/tiers`, { subject, entries },
    )
  },
  history(classId: number, subject: string, studentId: number) {
    return getData<{ items: Array<{ from_level: string | null; to_level: string; actor_user_id: number; changed_at: string }> }>(
      `/learning/classes/${classId}/tier-history`, { subject, student_id: studentId },
    )
  },
  variants(assignmentId: number) {
    return getData<{
      allow_uniform_fallback: boolean
      uniform_fallback_level: 'L1' | 'L2' | 'L3' | null
      variants: AssignmentVariant[]
    }>(`/learning/assignments/${assignmentId}/variants`)
  },
  saveVariants(assignmentId: number, body: {
    allow_uniform_fallback: boolean
    uniform_fallback_level: 'L1' | 'L2' | 'L3' | null
    variants: Array<{ level: 'L1' | 'L2' | 'L3'; questions: VariantQuestion[] }>
  }) {
    return putData<{ variants: AssignmentVariant[] }>(`/learning/assignments/${assignmentId}/variants`, body)
  },
  async downloadPdf(assignmentId: number, level: 'L1' | 'L2' | 'L3') {
    const response = await client.get<Blob>(
      `/learning/assignments/${assignmentId}/variants/${level}/print.pdf`,
      { responseType: 'blob' },
    )
    return response.data
  },
}
