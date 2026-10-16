<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { statsApi, type UserStats, type GlobalStats } from '@/api/statistics'
import { useAuthStore } from '@/stores/auth'
import StatsCard from '@/components/StatsCard.vue'

const auth = useAuthStore()
const userStats = ref<UserStats | null>(null)
const globalStats = ref<GlobalStats | null>(null)
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    if (auth.user) {
      const [uRes, gRes] = await Promise.all([
        statsApi.getUserStats(auth.user.id),
        statsApi.getGlobalStats(),
      ])
      userStats.value = uRes.data.data
      globalStats.value = gRes.data.data
    }
  } catch (e: any) {
    error.value = e.response?.data?.message || '获取统计数据失败'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div>
    <div class="page-header">
      <h1>数据统计</h1>
      <p>查看批改数据和平台概览</p>
    </div>

    <div v-if="error" class="error-message" role="alert">{{ error }}</div>

    <div v-if="loading" style="text-align:center;padding:48px;" role="status">
      <span class="spinner" aria-label="加载中"></span>
    </div>

    <template v-else>
      <h3 style="font-size:0.88rem;font-weight:600;color:var(--color-text-secondary);margin-bottom:12px;text-transform:uppercase;letter-spacing:0.04em;">
        我的统计
      </h3>
      <div class="stats-grid">
        <StatsCard :value="userStats?.task_count ?? 0" label="提交任务数" color="#2563eb">
          <template #icon>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="16" y1="13" x2="8" y2="13"/>
              <line x1="16" y1="17" x2="8" y2="17"/>
            </svg>
          </template>
        </StatsCard>
        <StatsCard :value="userStats?.completed_count ?? 0" label="已完成数" color="#059669">
          <template #icon>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
          </template>
        </StatsCard>
        <StatsCard :value="(userStats?.avg_score ?? 0).toFixed(1)" label="平均分" color="#d97706">
          <template #icon>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="20" x2="18" y2="10"/>
              <line x1="12" y1="20" x2="12" y2="4"/>
              <line x1="6" y1="20" x2="6" y2="14"/>
            </svg>
          </template>
        </StatsCard>
        <StatsCard :value="(userStats?.latest_score ?? 0).toFixed(1)" label="最近得分" color="#7c3aed">
          <template #icon>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
            </svg>
          </template>
        </StatsCard>
      </div>

      <h3 style="font-size:0.88rem;font-weight:600;color:var(--color-text-secondary);margin-bottom:12px;margin-top:32px;text-transform:uppercase;letter-spacing:0.04em;">
        平台概览
      </h3>
      <div class="stats-grid">
        <StatsCard :value="globalStats?.user_count ?? 0" label="用户总数" color="#2563eb">
          <template #icon>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
              <circle cx="9" cy="7" r="4"/>
              <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
              <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
            </svg>
          </template>
        </StatsCard>
        <StatsCard :value="globalStats?.task_count ?? 0" label="任务总数" color="#0891b2">
          <template #icon>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
              <line x1="3" y1="9" x2="21" y2="9"/>
              <line x1="9" y1="21" x2="9" y2="9"/>
            </svg>
          </template>
        </StatsCard>
        <StatsCard :value="globalStats?.completed_count ?? 0" label="已完成数" color="#059669">
          <template #icon>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
          </template>
        </StatsCard>
        <StatsCard :value="(globalStats?.avg_score ?? 0).toFixed(1)" label="平台平均分" color="#d97706">
          <template #icon>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="20" x2="18" y2="10"/>
              <line x1="12" y1="20" x2="12" y2="4"/>
              <line x1="6" y1="20" x2="6" y2="14"/>
            </svg>
          </template>
        </StatsCard>
      </div>
    </template>
  </div>
</template>
