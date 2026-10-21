<script setup lang="ts">
import { subjectLabel } from '@/student/workbench'
defineProps<{ subjects: string[]; modelValue: string }>()
defineEmits<{ 'update:modelValue': [value: string] }>()
</script>
<template>
  <nav class="subjects" aria-label="学科导航">
    <button type="button" :aria-pressed="!modelValue" @click="$emit('update:modelValue', '')">全部学科</button>
    <button v-for="subject in subjects" :key="subject" type="button" :aria-pressed="modelValue === subject" @click="$emit('update:modelValue', subject)">{{ subjectLabel(subject) }}</button>
  </nav>
</template>
<style scoped>
.subjects{display:flex;gap:8px;flex-wrap:wrap}.subjects button{padding:9px 15px;border:1px solid #dde6e1;border-radius:999px;background:#fff;color:#52655d;cursor:pointer;font:inherit;font-size:13px}.subjects button[aria-pressed=true]{background:#185d49;border-color:#185d49;color:white}.subjects button:focus-visible{outline:3px solid #9ec7b6;outline-offset:2px}
</style>
