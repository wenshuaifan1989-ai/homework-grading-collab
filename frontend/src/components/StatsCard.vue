<script setup lang="ts">
defineProps<{
  label: string
  value: string | number
  color?: string
}>()
</script>

<template>
  <div class="stat-card">
    <div
      class="stat-icon"
      :style="{ background: (color || '#2563eb') + '14', color: color || '#2563eb' }"
    >
      <slot name="icon">
        <!-- default fallback icon -->
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <line x1="12" y1="8" x2="12" y2="12"/>
          <line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
      </slot>
    </div>
    <div class="stat-value">{{ value }}</div>
    <div class="stat-label">{{ label }}</div>
  </div>
</template>
