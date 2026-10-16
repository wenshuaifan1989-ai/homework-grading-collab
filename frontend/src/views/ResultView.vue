<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useHomeworkStore } from '@/stores/homework'
import GradingCard from '@/components/GradingCard.vue'

const route = useRoute()
const homework = useHomeworkStore()
const taskId = route.params.taskId as string
const error = ref('')

const totalQuestions = computed(() => {
  return homework.currentResult?.results?.length || 0
})

const correctCount = computed(() => {
  return homework.currentResult?.results?.filter(r => r.result === '正确').length || 0
})

onMounted(async () => {
  try {
    await homework.fetchResult(taskId)
  } catch (e: any) {
    error.value = e.response?.data?.message || '获取结果失败'
  }
})
</script>

<template>
  <div>
    <div class="page-header">
      <h1>批改结果</h1>
      <p>任务 ID: {{ taskId }}</p>
    </div>

    <div v-if="error" class="error-message" role="alert">{{ error }}</div>

    <div v-if="homework.loading" style="text-align:center;padding:48px;" role="status">
      <span class="spinner" aria-label="加载批改结果中"></span>
    </div>

    <template v-else-if="homework.currentResult">
      <div class="card" style="margin-bottom:20px;">
        <div class="result-summary">
          <div>
            <div class="total-label">正确率</div>
            <div class="total-score" :class="{ 'high': (homework.currentResult.total_accuracy || 0) >= 80, 'medium': (homework.currentResult.total_accuracy || 0) >= 60 && (homework.currentResult.total_accuracy || 0) < 80, 'low': (homework.currentResult.total_accuracy || 0) < 60 }">
              {{ homework.currentResult.total_accuracy == null ? '待统计' : `${homework.currentResult.total_accuracy.toFixed(1)}%` }}
            </div>
          </div>
          <div style="font-size:0.85rem;color:var(--color-text-secondary);">
            共 {{ totalQuestions }} 题，答对 {{ correctCount }} 题
          </div>
        </div>
      </div>

      <div class="grading-list" role="list" aria-label="题目批改结果">
        <div v-for="r in homework.currentResult.results" :key="r.question_block_id" role="listitem">
          <GradingCard :item="r" />
        </div>
      </div>
    </template>

    <div v-else class="empty-state">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <polyline points="14 2 14 8 20 8"/>
        <line x1="16" y1="13" x2="8" y2="13"/>
        <line x1="16" y1="17" x2="8" y2="17"/>
      </svg>
      <p>暂无结果数据</p>
    </div>
  </div>
</template>
