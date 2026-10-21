<script setup lang="ts">
import { subjectLabel } from '@/student/workbench'
defineProps<{ subjects: string[]; modelValue: string; vertical?: boolean; counts?: Record<string, number> }>()
defineEmits<{ 'update:modelValue': [value: string] }>()
</script>
<template>
  <nav class="subjects" :class="{ vertical }" aria-label="学科导航">
    <button type="button" :aria-pressed="!modelValue" @click="$emit('update:modelValue', '')"><span>全部学科</span><small v-if="counts">{{ counts[''] ?? 0 }}</small></button>
    <button v-for="subject in subjects" :key="subject" type="button" :aria-pressed="modelValue === subject" @click="$emit('update:modelValue', subject)"><span>{{ subjectLabel(subject) }}</span><small v-if="counts">{{ counts[subject] ?? 0 }}</small></button>
  </nav>
</template>
<style scoped>
.subjects{display:flex;gap:8px;flex-wrap:wrap}
.subjects button{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:38px;padding:8px 12px;border:1px solid #dde6e1;border-radius:8px;background:#fff;color:#52655d;cursor:pointer;font:inherit;font-size:13px}
.subjects small{font-size:11px;opacity:.8;font-variant-numeric:tabular-nums}
.subjects button[aria-pressed=true]{background:#e0eee5;border-color:#b8d6c4;color:#185d49;font-weight:600}
.subjects button:focus-visible{outline:3px solid #9ec7b6;outline-offset:2px}
.vertical{display:grid;gap:6px}
.vertical button{width:100%;background:transparent;border-color:transparent}
.vertical button[aria-pressed=true]{background:#e0eee5;border-color:#c8dfcf}
@container(min-width:230px){.vertical{display:flex;flex-wrap:wrap}.vertical button{width:auto;border-color:#dde6e1}}
</style>
