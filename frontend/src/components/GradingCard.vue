<script setup lang="ts">
import { computed } from 'vue'
import type { GradingResultItem } from '@/api/homework'

const props = defineProps<{
  item: GradingResultItem
}>()

const resultClass = computed(() => {
  if (props.item.result === '正确') return 'result-correct'
  if (props.item.result === '部分正确') return 'result-partial'
  return 'result-incorrect'
})

const resultIcon = computed(() => {
  if (props.item.result === '正确') return 'check'
  if (props.item.result === '部分正确') return 'minus'
  return 'x'
})

const accuracy = computed(() => {
  if (props.item.max_score > 0) {
    return (props.item.score / props.item.max_score) * 100
  }
  return 0
})

const resultAriaLabel = computed(() => {
  return `第${props.item.question_no}题，${props.item.result}，得分${props.item.score}/${props.item.max_score}`
})
</script>

<template>
  <div class="grading-card" :class="resultClass" role="article" :aria-label="resultAriaLabel">
    <div class="gc-header">
      <span class="gc-qno">第 {{ item.question_no }} 题</span>
      <div style="display:flex;align-items:center;gap:6px;">
        <svg v-if="resultIcon === 'check'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="width:18px;height:18px;color:var(--color-success);" aria-hidden="true">
          <polyline points="20 6 9 17 4 12"/>
        </svg>
        <svg v-else-if="resultIcon === 'minus'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="width:18px;height:18px;color:var(--color-warning);" aria-hidden="true">
          <line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="width:18px;height:18px;color:var(--color-danger);" aria-hidden="true">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
        <span class="gc-score">
          {{ item.result }}
          <span class="gc-max">({{ item.score }}/{{ item.max_score }})</span>
        </span>
      </div>
    </div>
    
    <div v-if="item.question_text" class="gc-question">
      <div class="gc-label">题目</div>
      <div class="gc-text">{{ item.question_text }}</div>
    </div>
    
    <div v-if="item.student_answer" class="gc-student-answer">
      <div class="gc-label">学生答案</div>
      <div class="gc-text">{{ item.student_answer }}</div>
    </div>
    
    <div v-if="item.comment" class="gc-comment">{{ item.comment }}</div>
    <div v-if="item.analysis" class="gc-analysis">{{ item.analysis }}</div>
  </div>
</template>
