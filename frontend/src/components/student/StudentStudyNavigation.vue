<script setup lang="ts">
import StudentSubjectFilter from './StudentSubjectFilter.vue'
defineProps<{
  page: 'assignments' | 'mistakes' | 'profile'
  subjects: string[]
  modelValue: string
  counts?: Record<string, number>
}>()
defineEmits<{ 'update:modelValue': [value: string] }>()
</script>
<template>
  <section v-if="page!=='profile'" class="study-subjects" :aria-label="page === 'assignments' ? '作业学科筛选' : '错题学科筛选'">
    <p class="menu-caption">{{ page === 'assignments' ? '作业学科' : '错题学科' }}</p>
    <StudentSubjectFilter :subjects="subjects" :model-value="modelValue" :counts="counts" :allow-all="page!=='mistakes'" @update:model-value="$emit('update:modelValue', $event)" />
    <p v-if="!subjects.length" class="menu-note">读取后显示已有学科</p>
  </section>
</template>
<style scoped>
.study-subjects{display:flex;align-items:center;flex-wrap:wrap;gap:12px;padding:14px 16px;border:1px solid #dfe8e2;border-radius:12px;background:#f6faf7}
.menu-caption{margin:0;font-size:12px;color:#6a8073;white-space:nowrap}
.menu-note{font-size:12px;line-height:1.7;color:#76887c;margin:0}
@media(max-width:580px){.study-subjects{padding:12px;align-items:flex-start}.menu-caption{width:100%}}
</style>
