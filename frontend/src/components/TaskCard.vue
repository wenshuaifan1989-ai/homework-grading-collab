<script setup lang="ts">
import { computed } from 'vue'
import type { TaskItem } from '@/api/homework'

const props = defineProps<{
  task: TaskItem
}>()

const statusLabel = computed(() => {
  const map: Record<string, string> = {
    PENDING: '排队中',
    PROCESSING: '处理中',
    PREPROCESSING: '图像预处理',
    CUTTING: '题目切割',
    OCRING: '文字识别',
    GRADING: '批改中',
    SUCCESS: '已完成',
    FAILED: '失败',
  }
  return map[props.task.status] || props.task.status
})

const accuracyClass = computed(() => {
  if (props.task.status !== 'SUCCESS') return ''
  if (props.task.accuracy >= 80) return 'high'
  if (props.task.accuracy >= 60) return 'medium'
  return 'low'
})

const subjectLabel: Record<string, string> = {
  math: '数学', chinese: '语文', english: '英语',
  physics: '物理', chemistry: '化学',
}
const gradeLabel: Record<string, string> = {
  grade1: '一年级', grade2: '二年级', grade3: '三年级',
  grade4: '四年级', grade5: '五年级', grade6: '六年级',
  grade7: '七年级', grade8: '八年级', grade9: '九年级',
}
</script>

<template>
  <div
    class="task-item"
    role="button"
    tabindex="0"
    :aria-label="`任务 ${task.task_id}，${subjectLabel[task.subject] || task.subject}，状态 ${statusLabel}`"
    @keydown.enter="$emit('click')"
    @keydown.space.prevent="$emit('click')"
  >
    <div class="task-info">
      <div class="task-meta">
        <span>{{ subjectLabel[task.subject] || task.subject }}</span>
      </div>
      <div class="task-id">{{ task.task_id }}</div>
      <div v-if="task.status === 'SUCCESS'" class="task-score">
        <span :class="accuracyClass">正确率 {{ (task.accuracy ?? 0).toFixed(1) }}%</span>
        <span>{{ task.question_count }} 道题</span>
      </div>
    </div>
    <span class="badge" :class="'badge-' + task.status.toLowerCase().split(' ')[0]" role="status">
      {{ statusLabel }}
    </span>
  </div>
</template>
