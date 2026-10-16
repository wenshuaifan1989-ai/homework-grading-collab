<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const availableRoles = computed(() => [
  ...(auth.isTeacher ? [{ role: 'teacher' as const, path: '/teacher', label: '教师' }] : []),
  ...(auth.isStudent ? [{ role: 'student' as const, path: '/student', label: '学生' }] : []),
  ...(auth.isPlatformAdmin ? [{ role: 'platform_admin' as const, path: '/admin', label: '系统管理员' }] : []),
])
const teacherNavigation = [
  ['/teacher', '工作台'], ['/teacher/classes', '班级学生'],
  ['/teacher/assignments', '作业管理'], ['/teacher/data', '教学数据'], ['/teacher/bank', '题库与AI'],
]
function handleLogout() { auth.logout(); router.push('/') }
async function switchRole(role: 'teacher' | 'student' | 'platform_admin', path: string) {
  try { if (await auth.authorizeRole(role)) await router.push(path) }
  catch { auth.logout(); await router.push({ path: '/', query: { role: role === 'platform_admin' ? 'admin' : role } }) }
}
</script>
<template>
  <div class="app-shell">
    <aside class="sidebar" aria-label="主导航">
      <div class="sidebar-brand">作业批改系统</div>
      <nav class="sidebar-nav" aria-label="主导航菜单">
        <template v-if="auth.activeRole === 'teacher' && auth.isTeacher">
          <router-link v-for="item in teacherNavigation" :key="item[0]" :to="item[0]"
            :class="{ active: $route.path === item[0] }">{{ item[1] }}</router-link>
        </template>
        <template v-if="auth.activeRole === 'student' && auth.isStudent">
          <router-link to="/student">我的作业</router-link>
          <router-link to="/student/mistakes">错题与订正</router-link>
        </template>
        <router-link v-if="auth.activeRole === 'platform_admin' && auth.isPlatformAdmin" to="/admin">平台管理</router-link>
      </nav>
      <div class="sidebar-footer"><span>{{ auth.user?.username }}</span>
        <details v-if="availableRoles.length > 1"><summary>账户身份</summary>
          <button v-for="item in availableRoles.filter(r => r.role !== auth.activeRole)" :key="item.role" @click="switchRole(item.role,item.path)">进入{{ item.label }}空间</button>
        </details>
        <button @click="handleLogout" aria-label="退出登录">退出</button></div>
    </aside>
    <main class="main-content" role="main"><slot /></main>
  </div>
</template>
<style scoped>
.sidebar-footer{flex-wrap:wrap;gap:10px}.sidebar-footer>span{overflow-wrap:anywhere;width:100%}.sidebar-footer details{flex:1;min-width:110px}.sidebar-footer summary{cursor:pointer;white-space:nowrap}.sidebar-footer details button{display:block;white-space:nowrap;margin-top:8px}
</style>
