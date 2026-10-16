import client from './client'

type Envelope<T> = { code: number; message: string; data: T }
async function getData<T>(path: string, params?: Record<string, unknown>): Promise<T> {
  const response = await client.get<Envelope<T>>(path, { params })
  return response.data.data
}
async function postData<T>(path: string, body?: unknown): Promise<T> {
  const response = await client.post<Envelope<T>>(path, body)
  return response.data.data
}

export interface Classroom {
  id: number
  name: string
  invite_code: string
  grade?: string | null
  teacher_role?: string
  member_count: number
}
export interface RosterStudent {
  id: number
  student_id: number | null
  student_name: string
  student_no?: string | null
  bound: boolean
  bound_user_name?: string | null
  status: string
}
export interface Assignment {
  id: number
  title: string
  description?: string | null
  subject: string
  grade: string
  assignment_date: string
  due_at?: string | null
  status: string
  submission_count?: number
}
export interface Submission {
  student_id: number | null
  student_entity_id: number | null
  student_name: string
  student_no?: string | null
  submitted: boolean
  task_id?: string | null
  task_status?: string | null
  submitted_at?: string | null
  total_score?: number | null
}
export interface CalendarDay {
  date: string
  assignment_count: number
  assignment_ids: number[]
}

export const teacherApi = {
  classes: () => getData<Classroom[]>('/classes/mine'),
  createClass: (body: Record<string, unknown>) => postData<Classroom>('/classes', body),
  roster: (classId: number) => getData<RosterStudent[]>('/classes/' + classId + '/roster'),
  addStudent: (classId: number, body: { student_name: string; student_no?: string }) =>
    postData<RosterStudent>('/classes/' + classId + '/roster', body),
  addStudentsBatch: (classId: number, lines: string) =>
    postData<RosterStudent[]>('/classes/' + classId + '/roster/batch', { lines }),
  classTeachers: (classId: number) => getData<Array<{ user_id: number; name: string; role: string }>>(
    '/classes/' + classId + '/teachers',
  ),
  createTeacherInvite: (classId: number) =>
    postData<{ code: string; type: string }>('/classes/' + classId + '/contracts', { type: 'TEACHER_CLASS_JOIN' }),
  claimTeacherInvite: (code: string) =>
    postData<{ joined: boolean; already_joined?: boolean; class_id?: number }>(
      '/contracts/' + encodeURIComponent(code) + '/claim',
      { subject_codes: [] },
    ),
  assignments: (classId: number) =>
    getData<Assignment[]>('/classes/' + classId + '/assignments'),
  createAssignment: (classId: number, body: Record<string, unknown>) =>
    postData<Assignment>('/classes/' + classId + '/assignments', body),
  submissions: (assignmentId: number) =>
    getData<Submission[]>('/assignments/' + assignmentId + '/submissions'),
  studentResult: (assignmentId: number, studentId: number) =>
    getData<Record<string, any>>('/assignments/' + assignmentId + '/submissions/' + studentId + '/result'),
  studentEntityResult: (assignmentId: number, studentId: number) =>
    getData<Record<string, any>>('/assignments/' + assignmentId + '/students/' + studentId + '/result'),
  calendar: (classId: number, month: string) =>
    getData<{ month: string; dates: CalendarDay[] }>('/classes/' + classId + '/calendar', { month }),
  dailyDashboard: (classId: number, date: string) =>
    getData<Record<string, any>>('/classes/' + classId + '/daily-dashboard', { date }),
  questionStudents: (assignmentId: number, questionKey: string) =>
    getData<Record<string, any>>('/assignments/' + assignmentId + '/questions/' + encodeURIComponent(questionKey) + '/students'),
  originalImagePreview: (taskId: string, imageIndex: number) =>
    getData<{ storage: 'cos' | 'local'; url: string | null; expires_in: number | null }>(
      '/homework/image/' + taskId + '/preview-url',
      { image_index: imageIndex },
    ),
}
