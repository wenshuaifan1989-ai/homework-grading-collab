import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore, type PortalRole } from '@/stores/auth'

let validatedToken = ''

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'rolePortal',
      component: () => import('@/views/RolePortalView.vue'),
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('@/views/RegisterView.vue'),
      meta: { guest: true },
    },
    {
      path: '/teacher',
      name: 'teacherWorkspace',
      component: () => import('@/views/TeacherV2WorkspaceView.vue'),
      meta: { requiresAuth: true, requiresRole: 'teacher' },
    },
    ...['assignments', 'data', 'bank'].map(section => ({
      path: '/teacher/' + section,
      component: () => import('@/views/TeacherV2WorkspaceView.vue'),
      meta: { requiresAuth: true, requiresRole: 'teacher' },
    })),
    {
      path: '/teacher/classes',
      component: () => import('@/views/TeacherWorkspaceView.vue'),
      props: { initialTab: 'classes', classesOnly: true },
      meta: { requiresAuth: true, requiresRole: 'teacher' },
    },
    {
      path: '/teacher/legacy',
      redirect: '/teacher/data?panel=calendar',
      meta: { requiresAuth: true, requiresRole: 'teacher' },
    },
    {
      path: '/teacher/mistakes',
      name: 'teacherMistakes',
      redirect: '/teacher/assignments?panel=corrections',
      meta: { requiresAuth: true, requiresRole: 'teacher' },
    },
    {
      path: '/teacher/learning',
      name: 'teacherLearning',
      redirect: '/teacher/assignments',
      meta: { requiresAuth: true, requiresRole: 'teacher' },
    },
    {
      path: '/teacher/assignment-plans',
      name: 'teacherAssignmentPlans',
      redirect: '/teacher/bank?panel=assistant',
      meta: { requiresAuth: true, requiresRole: 'teacher' },
    },
    {
      path: '/teacher/known-assignments',
      name: 'teacherKnownAssignments',
      redirect: '/teacher/assignments',
      meta: { requiresAuth: true, requiresRole: 'teacher' },
    },
    {
      path: '/teacher/learning-advice',
      name: 'teacherLearningAdvice',
      redirect: '/teacher/data',
      meta: { requiresAuth: true, requiresRole: 'teacher' },
    },
    {
      path: '/result/:taskId',
      name: 'result',
      component: () => import('@/views/ResultView.vue'),
      meta: { requiresAuth: true, requiresRole: 'teacher' },
    },
    {
      path: '/statistics',
      name: 'statistics',
      redirect: '/teacher/data',
      meta: { requiresAuth: true, requiresRole: 'teacher' },
    },
    {
      path: '/admin',
      name: 'admin',
      component: () => import('@/views/PlatformAdminView.vue'),
      meta: { requiresAuth: true, requiresRole: 'platform_admin' },
    },
    {
      path: '/student',
      name: 'student',
      component: () => import('@/views/StudentWorkspaceView.vue'),
      meta: { requiresAuth: true, requiresRole: 'student' },
    },
    {
      path: '/student/mistakes',
      name: 'studentMistakes',
      component: () => import('@/views/StudentMistakesView.vue'),
      meta: { requiresAuth: true, requiresRole: 'student' },
    },
    { path: '/login', redirect: { path: '/', query: { role: 'teacher' } } },
    { path: '/admin/login', redirect: { path: '/', query: { role: 'admin' } } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  let token = localStorage.getItem('access_token')

  if (token && validatedToken !== token) {
    try {
      await auth.refreshIdentity()
      validatedToken = token
    } catch {
      auth.logout()
      validatedToken = ''
      token = null
    }
  }
  if (to.meta.requiresAuth && !token) return { path: '/', query: { role: roleForPath(to.path) } }
  const requiredRole = to.meta.requiresRole as PortalRole | undefined
  if (requiredRole && token) {
    try {
      if (await auth.authorizeRole(requiredRole)) return true
    } catch {
      auth.logout()
      validatedToken = ''
      return { path: '/', query: { role: roleForPath(to.path), reason: 'session' } }
    }
    return { path: '/', query: { role: roleForPath(to.path), reason: 'role' } }
  }
  return true
})

function roleForPath(path: string): string {
  if (path.startsWith('/admin')) return 'admin'
  if (path.startsWith('/student')) return 'student'
  return 'teacher'
}

export default router
