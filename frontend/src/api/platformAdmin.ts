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

export const platformAdminApi = {
  users: (q: string) => getData<any[]>('/admin/users', { q, limit: 100 }),
  students: (q: string) => getData<any[]>('/admin/students', { q, limit: 100 }),
  bindings: () => getData<any[]>('/admin/family-bindings'),
  schools: (q: string) => getData<any[]>('/admin/schools', { q }),
  contacts: (q: string) => getData<any[]>('/admin/contacts', { q, limit: 100 }),
  homework: (studentId?: number) => getData<any[]>('/admin/homework', { student_id: studentId, limit: 100 }),
  teachers: (q: string) => getData<any[]>('/admin/teachers', { q, limit: 100 }),
  classes: () => getData<any[]>('/admin/classes'),
  classRoster: (classId: number) => getData<any[]>('/classes/' + classId + '/roster'),
  setUserStatus: (userId: number, isActive: boolean) =>
    postData<any>('/admin/users/' + userId + '/status', { is_active: isActive }),
  correctFamilyBinding: (studentId: number, body: Record<string, unknown>) =>
    postData<any>('/admin/students/' + studentId + '/family-bindings', body),
  correctRosterStudent: (classId: number, rosterId: number, studentId: number | null) =>
    postData<any>('/admin/classes/' + classId + '/roster/' + rosterId + '/student', { student_id: studentId }),
  setTeacherStatus: (teacherId: number, isActive: boolean) =>
    postData<any>('/admin/teachers/' + teacherId + '/status', { is_active: isActive }),
  createTeacher: (body: { phone: string; password: string; full_name: string }) =>
    postData<any>('/admin/teachers', body),
}
