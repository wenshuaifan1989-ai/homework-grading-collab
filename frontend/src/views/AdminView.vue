<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { authApi, type User } from '@/api/auth'
import UserTable from '@/components/UserTable.vue'

const users = ref<User[]>([])
const loading = ref(false)
const error = ref('')
const searchId = ref('')

async function searchUser() {
  if (!searchId.value) {
    error.value = '请输入用户 ID 进行搜索'
    return
  }
  error.value = ''
  loading.value = true
  try {
    const { data } = await authApi.getUser(Number(searchId.value))
    users.value = [data]
  } catch (e: any) {
    error.value = e.response?.data?.message || '未找到该用户'
    users.value = []
  } finally {
    loading.value = false
  }
}

async function toggleStatus(userId: number, currentActive: boolean) {
  try {
    const { data } = await authApi.updateUserStatus(userId, !currentActive)
    const idx = users.value.findIndex((u) => u.id === userId)
    if (idx !== -1) users.value[idx] = data
  } catch (e: any) {
    error.value = e.response?.data?.message || '操作失败'
  }
}

onMounted(() => {
  searchId.value = '1'
  searchUser()
})
</script>

<template>
  <div>
    <div class="page-header">
      <h1>用户管理</h1>
      <p>管理系统用户账号</p>
    </div>

    <div v-if="error" class="error-message" role="alert">{{ error }}</div>

    <div class="card" style="margin-bottom:20px;">
      <form @submit.prevent="searchUser">
        <div style="display:flex;gap:12px;align-items:flex-end;">
          <div class="form-group" style="margin-bottom:0;flex:1;">
            <label class="form-label" for="admin-search-id">用户 ID</label>
            <input
              id="admin-search-id"
              v-model="searchId"
              class="form-input"
              type="number"
              placeholder="输入用户 ID 进行搜索"
            />
          </div>
          <button class="btn btn-primary" type="submit" aria-label="搜索用户">查询</button>
        </div>
      </form>
    </div>

    <UserTable :users="users" :loading="loading" @toggle-status="toggleStatus" />
  </div>
</template>
