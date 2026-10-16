<script setup lang="ts">
import type { TaskItem } from '@/api/homework'
import TaskCard from './TaskCard.vue'

defineProps<{
  tasks: TaskItem[]
}>()
</script>

<template>
  <div class="card">
    <div class="card-header">批改记录</div>
    <div v-if="tasks.length === 0" class="empty-state">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <polyline points="14 2 14 8 20 8"/>
        <line x1="16" y1="13" x2="8" y2="13"/>
        <line x1="16" y1="17" x2="8" y2="17"/>
      </svg>
      <p>暂无批改记录</p>
    </div>
    <div v-else class="task-list" role="list" aria-label="批改任务列表">
      <div v-for="t in tasks" :key="t.task_id" role="listitem">
        <router-link :to="`/result/${t.task_id}`" style="text-decoration:none;color:inherit;display:block;">
          <TaskCard :task="t" />
        </router-link>
      </div>
    </div>
  </div>
</template>
