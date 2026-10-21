<script setup lang="ts">
import { ref } from 'vue'
import StudentSubjectFilter from './StudentSubjectFilter.vue'
import { subjectLabel } from '@/student/workbench'
defineProps<{
  page: 'assignments' | 'mistakes'
  subjects: string[]
  modelValue: string
  counts?: Record<string, number>
}>()
defineEmits<{ 'update:modelValue': [value: string] }>()
const subjectsExpanded = ref(false)
</script>
<template>
  <div class="study-menu">
    <p class="menu-caption">{{ page === 'assignments' ? '作业学科' : '错题学科' }}</p>
    <button type="button" class="subject-toggle" :aria-expanded="subjectsExpanded" @click="subjectsExpanded = !subjectsExpanded">
      <span>学科：{{ modelValue ? subjectLabel(modelValue) : '全部学科' }}</span><span>{{ subjectsExpanded ? '收起 −' : '切换 +' }}</span>
    </button>
    <div class="subject-section" :class="{ expanded: subjectsExpanded }">
      <StudentSubjectFilter :subjects="subjects" :model-value="modelValue" :counts="counts" vertical @update:model-value="$emit('update:modelValue', $event)" />
      <p v-if="!subjects.length" class="menu-note">读取后显示已有学科</p>
    </div>
    <p class="menu-note">{{ page === 'assignments' ? '查看老师布置的作业，按要求完成后提交。' : '回看本人作答，订正后查看老师审核记录。' }}</p>
  </div>
</template>
<style scoped>
.study-menu{container-type:inline-size;padding:14px 8px;border:1px solid #dfe8e2;border-radius:12px;background:#f6faf7}
.menu-caption{margin:0 10px 12px;font-size:11px;letter-spacing:.08em;color:#6a8073}
.subject-section{margin-top:0}
.subject-toggle{display:none}
.menu-note{font-size:11px;line-height:1.8;color:#76887c;margin:20px 10px 4px}
@container(min-width:230px){
  .menu-caption{margin-bottom:8px}
  .subject-toggle{display:flex;justify-content:space-between;align-items:center;gap:12px;width:100%;min-height:38px;padding:8px 10px;border:1px solid #d7e4da;background:#fff;border-radius:8px;font:inherit;font-size:12px;color:#456351;cursor:pointer}
  .subject-toggle:focus-visible{outline:3px solid #9ec7b6;outline-offset:2px}
  .subject-section{display:none;margin-top:10px;padding-top:12px}
  .subject-section.expanded{display:block}
  .menu-note{display:none}
}
</style>
