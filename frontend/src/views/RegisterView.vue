<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

const phone = ref('')
const email = ref('')
const password = ref('')
const confirmPassword = ref('')
const fullName = ref('')
const error = ref('')
const loading = ref(false)

async function handleRegister() {
  error.value = ''
  if (!phone.value || !password.value) {
    error.value = '请填写手机号和密码。'
    return
  }
  if (password.value !== confirmPassword.value) {
    error.value = '两次密码不一致'
    return
  }
  if (password.value.length < 8) {
    error.value = '密码至少需要 8 位。'
    return
  }
  loading.value = true
  try {
    await auth.register(phone.value, password.value, fullName.value, email.value || undefined)
    await auth.login(phone.value, password.value)
    if (!await auth.authorizeRole('student')) {
      auth.logout()
      throw new Error('学生身份验证失败，请联系管理员。')
    }
    await router.replace('/student')
  } catch (e: any) {
    error.value = e.response?.data?.detail || e.response?.data?.message || e.message || '注册失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <h2>注册</h2>
      <p class="auth-subtitle">仅注册学生手机号账号</p>

      <div v-if="error" class="error-message" role="alert">{{ error }}</div>

      <form @submit.prevent="handleRegister" novalidate>
        <div class="form-group">
          <label class="form-label" for="reg-phone">手机号 *</label>
          <input id="reg-phone" v-model="phone" class="form-input" inputmode="tel" autocomplete="tel" placeholder="请输入手机号" required />
        </div>
        <div class="form-group">
          <label class="form-label" for="reg-email">邮箱（选填）</label>
          <input id="reg-email" v-model="email" class="form-input" type="email" placeholder="选填" />
        </div>
        <div class="form-group">
          <label class="form-label" for="reg-name">姓名</label>
          <input id="reg-name" v-model="fullName" class="form-input" placeholder="请输入姓名（选填）" />
        </div>
        <div class="form-group">
          <label class="form-label" for="reg-password">密码 *</label>
          <input id="reg-password" v-model="password" class="form-input" type="password" autocomplete="new-password" placeholder="至少8位" required />
        </div>
        <div class="form-group">
          <label class="form-label" for="reg-confirm">确认密码 *</label>
          <input id="reg-confirm" v-model="confirmPassword" class="form-input" type="password" placeholder="请再次输入密码" required />
        </div>
        <button class="btn btn-primary btn-block" :disabled="loading" type="submit" aria-label="注册">
          <span v-if="loading" class="spinner" aria-hidden="true"></span>
          {{ loading ? '注册中...' : '注册' }}
        </button>
      </form>

      <p class="auth-link">
        已有账号？<router-link to="/?role=student">立即登录</router-link>
      </p>
    </div>
  </div>
</template>
