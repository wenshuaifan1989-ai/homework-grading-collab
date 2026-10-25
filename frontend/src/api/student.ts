import client from './client'
import type { GradingResultResponse, TaskStatusResponse } from './homework'

export interface StudentClass {
  class_id: number
  class_name: string
  status: string
}

export interface LinkedStudent {
  student_id: number
  name: string
  relationship_type: string
  relationship_label?: string | null
  status: string
  classes: StudentClass[]
}

export interface StudentAssignment {
  id: number
  class_id: number
  class_name: string
  title: string
  description?: string | null
  subject: string
  grade: string
  assignment_date?: string | null
  due_at?: string | null
  status: string
  submitted: boolean
  task_id?: string | null
  task_status?: string | null
  submitted_at?: string | null
  student_id?: number | null
  student_name?: string | null
  roster_id?: number
  variant_mode?: boolean
  variant_available?: boolean
  assignment_mode?: string
  original_format?: string
  variant_questions?: Array<{
    id: number
    number: number | string
    question_text: string
    options?: string[] | null
    max_score: number
    requirement?: 'required' | 'optional'
    requirement_label?: string
  }>
  variant_message?: string | null
}

export interface StudentBinding {
  is_bound: boolean
  class_id?: number
  class_name?: string
  roster_id?: number
  student_id?: number | null
  student_name?: string
  student_no?: string | null
}

export interface RosterOption {
  id: number
  student_name: string
  student_no?: string | null
  class_id: number
  class_name?: string
}

export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export const studentApi = {
  getMyStudents() {
    return client.get<ApiResponse<LinkedStudent[]>>('/students/mine')
  },
  getBinding() {
    return client.get<ApiResponse<StudentBinding>>('/students/binding')
  },
  getBindingOptions(inviteCode: string, studentName: string) {
    return client.post<ApiResponse<{
      class_id: number
      class_name: string
      invite_code: string
      requires_name: boolean
      requires_disambiguation: boolean
      students: RosterOption[]
    }>>('/students/binding-options', { invite_code: inviteCode, student_name: studentName })
  },
  bind(inviteCode: string, studentName: string, rosterId: number) {
    return client.post<ApiResponse<StudentBinding & { bound: boolean }>>('/students/bind', {
      invite_code: inviteCode,
      student_name: studentName,
      roster_id: rosterId,
    })
  },
  getAssignments(studentId?: number) {
    const query = studentId ? `?student_id=${encodeURIComponent(studentId)}` : ''
    return client.get<ApiResponse<StudentAssignment[]>>(`/assignments/mine${query}`)
  },
  getPublishedPaper(assignmentId: number, studentId: number) {
    return client.get<Blob>(`/teacher-v2/assignments/${assignmentId}/source`, {
      params: { student_id: studentId },
      responseType: 'blob',
    })
  },
  createFamilyInvite(studentId: number) {
    return client.post<ApiResponse<{ code: string; expires_at?: string }>>(
      `/students/${studentId}/family-contract`, {},
    )
  },
  claimFamilyInvite(code: string, relationshipType: string) {
    return client.post<ApiResponse<{ bound: boolean; already_bound?: boolean; student_id: number }>>(
      `/contracts/${encodeURIComponent(code)}/claim`, { relationship_type: relationshipType },
    )
  },
  submitAssignment(formData: FormData, idempotencyKey?: string) {
    return client.post<ApiResponse<{ task_id: string; status: string; image_count: number }>>(
      '/homework/analyze', formData,
      idempotencyKey ? { headers: { 'Idempotency-Key': idempotencyKey } } : undefined,
    )
  },
  getStatus(taskId: string) {
    return client.get<ApiResponse<TaskStatusResponse>>(`/homework/status/${encodeURIComponent(taskId)}`)
  },
  getResult(taskId: string) {
    return client.get<ApiResponse<GradingResultResponse>>(`/homework/result/${encodeURIComponent(taskId)}`)
  },
  getOriginalImage(taskId: string, imageIndex: number) {
    return client.get<Blob>(`/homework/image/${encodeURIComponent(taskId)}`, {
      params: { image_index: imageIndex },
      responseType: 'blob',
    })
  },
}
