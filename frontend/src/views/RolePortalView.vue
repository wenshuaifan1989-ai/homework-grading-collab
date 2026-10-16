<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore, type PortalRole } from '@/stores/auth'

type PortalChoice = 'teacher' | 'student' | 'admin'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const selectedRole = ref<PortalChoice | null>(null)
const identifier = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

const roleInfo = computed(() => {
  if (selectedRole.value === 'teacher') return { title: '教师登录', label: '手机号' }
  if (selectedRole.value === 'student') return { title: '学生登录', label: '手机号' }
  if (selectedRole.value === 'admin') return { title: '系统管理员登录', label: '管理员用户名' }
  return null
})

watch(() => route.query.role, (value) => {
  if (value === 'teacher' || value === 'student' || value === 'admin') {
    selectedRole.value = value
    identifier.value = value === 'admin' ? 'superadmin' : ''
  }
}, { immediate: true })

watch(() => route.query.reason, (reason) => {
  if (reason === 'role') error.value = '当前账号没有该身份的使用权限，请选择已有身份或使用对应账号登录。'
  else if (reason === 'session') error.value = '登录状态已失效，请重新登录。'
}, { immediate: true })

function routeFor(role: PortalChoice) {
  return role === 'teacher' ? '/teacher' : role === 'student' ? '/student' : '/admin'
}

function storeRole(role: PortalChoice): PortalRole {
  return role === 'admin' ? 'platform_admin' : role
}

async function chooseRole(role: PortalChoice) {
  selectedRole.value = role
  identifier.value = role === 'admin' ? 'superadmin' : ''
  password.value = ''
  error.value = ''
  if (!auth.isLoggedIn) return
  loading.value = true
  try {
    if (await auth.authorizeRole(storeRole(role))) {
      await router.replace(routeFor(role))
      return
    }
    auth.logout()
  } catch {
    auth.logout()
  } finally {
    loading.value = false
  }
}

async function submitLogin() {
  if (!selectedRole.value) return
  error.value = ''
  if (!identifier.value.trim() || !password.value) {
    error.value = '请填写登录账号和密码。'
    return
  }
  loading.value = true
  auth.logout()
  try {
    await auth.login(
      identifier.value.trim(),
      password.value,
      selectedRole.value === 'admin' ? 'identifier' : 'phone',
    )
    const permitted = await auth.authorizeRole(storeRole(selectedRole.value))
    if (!permitted) {
      auth.logout()
      error.value = '账号或密码错误，或该账号没有所选身份的权限。'
      return
    }
    await router.replace(routeFor(selectedRole.value))
  } catch (requestError: any) {
    auth.logout()
    error.value = requestError.response?.data?.detail
      || requestError.response?.data?.message
      || '登录失败，请检查账号、密码和网络连接。'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="portal-page">
    <div class="portal-orb portal-orb-one" aria-hidden="true"></div>
    <div class="portal-orb portal-orb-two" aria-hidden="true"></div>
    <section class="portal-shell">
      <header class="portal-heading">
        <div class="portal-mark" aria-hidden="true">
          <svg viewBox="0 0 32 32" fill="none"><path d="M6 8.5A2.5 2.5 0 0 1 8.5 6H25v19H8.5A2.5 2.5 0 0 0 6 27.5v-19Z"/><path d="M6 24.5A2.5 2.5 0 0 1 8.5 22H25M11 11h9M11 15h9"/></svg>
        </div>
        <p class="portal-eyebrow">作业 · 学习 · 成长</p>
        <h1>作业智能管理平台</h1>
        <p class="portal-subtitle">请选择您的使用身份，进入对应工作空间</p>
      </header>

      <div class="portal-content">
        <section v-if="!selectedRole" class="portal-choices" aria-label="选择登录身份">
          <button class="portal-choice" type="button" @click="chooseRole('teacher')">
            <span class="portal-choice-icon teacher-icon" aria-hidden="true">师</span>
            <span class="portal-choice-copy"><strong>教师</strong><small>班级、作业与教学数据</small></span>
            <span class="portal-arrow" aria-hidden="true">›</span>
          </button>
          <button class="portal-choice" type="button" @click="chooseRole('student')">
            <span class="portal-choice-icon student-icon" aria-hidden="true">学</span>
            <span class="portal-choice-copy"><strong>学生</strong><small>查看作业、提交与批改结果</small></span>
            <span class="portal-arrow" aria-hidden="true">›</span>
          </button>
          <button class="portal-choice" type="button" @click="chooseRole('admin')">
            <span class="portal-choice-icon admin-icon" aria-hidden="true">管</span>
            <span class="portal-choice-copy"><strong>系统管理员</strong><small>账号、权限与平台设置</small></span>
            <span class="portal-arrow" aria-hidden="true">›</span>
          </button>
        </section>

        <section v-else class="portal-login" aria-live="polite">
          <button class="portal-back" type="button" @click="selectedRole = null; error = ''">← 返回身份选择</button>
          <div class="portal-login-title">
            <span class="portal-choice-icon" :class="`${selectedRole}-icon`" aria-hidden="true">
              {{ selectedRole === 'teacher' ? '师' : selectedRole === 'student' ? '学' : '管' }}
            </span>
            <div><h2>{{ roleInfo?.title }}</h2><p>使用已分配的账号登录</p></div>
          </div>
          <div v-if="error" class="portal-error" role="alert">{{ error }}</div>
          <form @submit.prevent="submitLogin">
            <label class="portal-label" for="portal-identifier">{{ roleInfo?.label }}</label>
            <input
              id="portal-identifier"
              v-model="identifier"
              class="portal-input"
              :autocomplete="selectedRole === 'admin' ? 'username' : 'tel'"
              :inputmode="selectedRole === 'admin' ? 'text' : 'tel'"
              :placeholder="selectedRole === 'admin' ? '请输入管理员用户名' : '请输入手机号'"
              required
            />
            <label class="portal-label" for="portal-password">密码</label>
            <input id="portal-password" v-model="password" class="portal-input" type="password" autocomplete="current-password" placeholder="请输入密码" required />
            <button class="portal-submit" type="submit" :disabled="loading">
              {{ loading ? '正在验证身份…' : '登录并进入工作台' }}
            </button>
          </form>
          <p v-if="selectedRole === 'student'" class="portal-register-hint">
            还没有学生账号？<router-link to="/register">注册学生账号</router-link>
          </p>
        </section>
      </div>

      <footer class="portal-footer"><span>作业智能管理平台</span><span>身份权限由服务端验证</span></footer>
    </section>
  </main>
</template>
