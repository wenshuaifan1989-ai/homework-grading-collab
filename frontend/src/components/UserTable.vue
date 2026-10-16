<script setup lang="ts">
import type { User } from '@/api/auth'

defineProps<{
  users: User[]
  loading: boolean
}>()

const emit = defineEmits<{
  toggleStatus: [userId: number, currentActive: boolean]
}>()

const roleLabel: Record<string, string> = {
  admin: '管理员',
  teacher: '教师',
  student: '学生',
}
</script>

<template>
  <div class="card">
    <div class="card-header">用户列表</div>
    <div class="table-wrapper">
      <table aria-label="用户列表">
        <thead>
          <tr>
            <th>ID</th>
            <th>用户名</th>
            <th>邮箱</th>
            <th>姓名</th>
            <th>角色</th>
            <th>状态</th>
            <th>创建时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td colspan="8" style="text-align:center;padding:40px;" role="status">
              <span class="spinner" aria-label="加载用户列表"></span>
            </td>
          </tr>
          <tr v-else-if="users.length === 0">
            <td colspan="8" style="text-align:center;padding:40px;color:var(--color-text-muted);">
              暂无用户数据
            </td>
          </tr>
          <tr v-for="u in users" :key="u.id" v-else>
            <td>
              <span style="font-family:'SF Mono','Fira Code',monospace;font-size:0.8rem;">{{ u.id }}</span>
            </td>
            <td>
              <strong>{{ u.username }}</strong>
            </td>
            <td>{{ u.email }}</td>
            <td>{{ u.full_name || '-' }}</td>
            <td>
              <span class="badge" :class="u.role === 'admin' ? 'badge-success' : u.role === 'teacher' ? 'badge-processing' : 'badge-pending'">
                {{ roleLabel[u.role] || u.role }}
              </span>
            </td>
            <td>
              <span class="badge" :class="u.is_active ? 'badge-success' : 'badge-failed'">
                {{ u.is_active ? '正常' : '禁用' }}
              </span>
            </td>
            <td>{{ new Date(u.created_at).toLocaleDateString('zh-CN') }}</td>
            <td>
              <button
                class="btn btn-sm"
                :class="u.is_active ? 'btn-danger' : 'btn-primary'"
                :aria-label="u.is_active ? `禁用用户 ${u.username}` : `启用用户 ${u.username}`"
                @click="emit('toggleStatus', u.id, u.is_active)"
              >
                {{ u.is_active ? '禁用' : '启用' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
