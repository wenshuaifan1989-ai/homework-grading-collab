import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi, type User } from '@/api/auth'
import { studentApi } from '@/api/student'

export type PortalRole = 'teacher' | 'student' | 'platform_admin'

function initialUser(): User | null {
  try {
    return JSON.parse(localStorage.getItem('user') || 'null') as User | null
  } catch {
    return null
  }
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(initialUser())
  const token = ref<string | null>(localStorage.getItem('access_token'))
  const activeRole = ref<PortalRole | null>(sessionStorage.getItem('active_role') as PortalRole | null)
  const hasLinkedStudent = ref(user.value?.role === 'student')

  const isLoggedIn = computed(() => !!token.value)
  const roles = computed(() => user.value?.roles?.length
    ? user.value.roles
    : user.value?.role ? [user.value.role === 'admin' ? 'platform_admin' : user.value.role] : [])
  const isPlatformAdmin = computed(() => roles.value.includes('platform_admin') || user.value?.role === 'admin')
  const isTeacher = computed(() => roles.value.includes('teacher') || user.value?.role === 'teacher')
  const isStudent = computed(() => user.value?.role === 'student' || hasLinkedStudent.value)

  function setAuth(t: string, u: User) {
    token.value = t
    user.value = u
    hasLinkedStudent.value = u.role === 'student'
    localStorage.setItem('access_token', t)
    localStorage.setItem('user', JSON.stringify(u))
  }

  function setActiveRole(role: PortalRole | null) {
    activeRole.value = role
    if (role) sessionStorage.setItem('active_role', role)
    else sessionStorage.removeItem('active_role')
  }

  function setLinkedStudentAccess(value: boolean) {
    hasLinkedStudent.value = value || user.value?.role === 'student'
  }

  function logout() {
    token.value = null
    user.value = null
    hasLinkedStudent.value = false
    setActiveRole(null)
    localStorage.removeItem('access_token')
    localStorage.removeItem('user')
  }

  async function login(identifier: string, password: string, mode: 'phone' | 'identifier' = 'phone') {
    const credentials = mode === 'identifier'
      ? { identifier, password }
      : { phone: identifier, password }
    const { data } = await authApi.login(credentials)
    setAuth(data.access_token, data.user)
    return data.user
  }

  async function refreshIdentity() {
    const { data: serverUser } = await authApi.getMe()
    const currentToken = localStorage.getItem('access_token')
    if (!currentToken) throw new Error('登录状态已失效')
    setAuth(currentToken, serverUser)
    let linked = serverUser.role === 'student'
    try {
      const { data } = await studentApi.getMyStudents()
      linked = linked || (Array.isArray(data.data) && data.data.length > 0)
    } catch {
      // The server endpoint remains authoritative; a failed lookup grants no family-student access.
    }
    setLinkedStudentAccess(linked)
    return serverUser
  }

  async function authorizeRole(role: PortalRole): Promise<boolean> {
    const serverUser = await refreshIdentity()
    const serverRoles = serverUser.roles || []
    const allowed = role === 'platform_admin'
      ? serverRoles.includes('platform_admin') || serverUser.role === 'admin'
      : role === 'teacher'
        ? serverRoles.includes('teacher') || serverUser.role === 'teacher'
        : serverUser.role === 'student' || hasLinkedStudent.value
    if (allowed) setActiveRole(role)
    return allowed
  }

  async function register(phone: string, password: string, fullName?: string, email?: string) {
    const { data } = await authApi.register({ phone, password, full_name: fullName, email, role: 'student' })
    return data
  }

  return {
    user, token, activeRole, roles, isLoggedIn, isPlatformAdmin, isTeacher, isStudent,
    setAuth, setActiveRole, setLinkedStudentAccess, refreshIdentity, authorizeRole,
    logout, login, register,
  }
})
