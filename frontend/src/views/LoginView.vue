<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const account = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)
const adminSurface = computed(() => route.path.startsWith('/admin/'))

async function handleLogin() {
  error.value = ''
  if (!account.value || !password.value) {
    error.value = adminSurface.value ? '请输入管理员账号和密码' : '请输入手机号和密码'
    return
  }
  loading.value = true
  try {
    const user = await auth.login(account.value, password.value, adminSurface.value ? 'identifier' : 'phone')
    if (adminSurface.value) {
      if (!user.roles?.includes('platform_admin') && user.role !== 'admin') {
        auth.logout()
        error.value = '该账号没有平台管理权限'
        return
      }
      router.push('/admin')
    } else if (user.roles?.includes('teacher') || user.role === 'teacher') {
      router.push('/')
    } else if (user.roles?.includes('platform_admin') || user.role === 'admin') {
      router.push('/admin')
    } else {
      auth.logout()
      error.value = '该账号没有教师 Web 权限'
    }
  } catch (e: any) {
    error.value = e.response?.data?.detail || e.response?.data?.message || '登录失败，请检查用户名和密码'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <h2>{{ adminSurface ? '平台管理登录' : '教师工作台登录' }}</h2>
      <p class="auth-subtitle">作业批改系统</p>

      <div v-if="error" class="error-message" role="alert">{{ error }}</div>

      <form @submit.prevent="handleLogin" novalidate>
        <div class="form-group">
          <label class="form-label" for="login-account">{{ adminSurface ? '管理员账号' : '手机号' }}</label>
          <input
            id="login-account"
            v-model="account"
            class="form-input"
            :placeholder="adminSurface ? '请输入管理员账号' : '请输入手机号'"
            :autocomplete="adminSurface ? 'username' : 'tel'"
            required
          />
        </div>
        <div class="form-group">
          <label class="form-label" for="login-password">密码</label>
          <input
            id="login-password"
            v-model="password"
            class="form-input"
            type="password"
            placeholder="请输入密码"
            autocomplete="current-password"
            required
          />
        </div>
        <button
          class="btn btn-primary btn-block"
          :disabled="loading"
          type="submit"
          aria-label="登录"
        >
          <span v-if="loading" class="spinner" aria-hidden="true"></span>
          {{ loading ? '登录中...' : '登录' }}
        </button>
      </form>

      <p v-if="!adminSurface" class="auth-link">
        学生账号请使用微信小程序完成注册与身份绑定。
      </p>
    </div>
  </div>
</template>
