<script setup lang="ts">
import StudentSubjectFilter from './StudentSubjectFilter.vue'
defineProps<{
  page: 'assignments' | 'mistakes'
  subjects: string[]
  modelValue: string
  counts?: Record<string, number>
}>()
defineEmits<{ 'update:modelValue': [value: string] }>()
</script>
<template>
  <div class="study-menu">
    <p class="menu-caption">学习空间</p>
    <nav class="page-links" aria-label="学生工作区页面">
      <router-link to="/student" :aria-current="page === 'assignments' ? 'page' : undefined">
        <span aria-hidden="true">▤</span>我的作业
      </router-link>
      <router-link to="/student/mistakes" :aria-current="page === 'mistakes' ? 'page' : undefined">
        <span aria-hidden="true">▧</span>我的错题库
      </router-link>
    </nav>
    <div class="subject-section">
      <p class="menu-caption">按学科查看</p>
      <StudentSubjectFilter :subjects="subjects" :model-value="modelValue" :counts="counts" vertical @update:model-value="$emit('update:modelValue', $event)" />
      <p v-if="!subjects.length" class="menu-note">读取后显示已有学科</p>
    </div>
    <p class="menu-note">{{ page === 'assignments' ? '查看老师布置的作业，按要求完成后提交。' : '回看本人作答，订正后查看老师审核记录。' }}</p>
  </div>
</template>
<style scoped>
.study-menu{container-type:inline-size;padding:16px 10px;border:1px solid #dfe8e2;border-radius:14px;background:#f6faf7}
.menu-caption{margin:0 10px 12px;font-size:11px;letter-spacing:.08em;color:#6a8073}
.page-links{display:grid;gap:6px}
.page-links a{display:flex;align-items:center;gap:9px;min-height:42px;padding:8px 10px;border-radius:8px;font-size:13px;font-weight:600;text-decoration:none;color:#456351}
.page-links a[aria-current=page]{background:#185d49;color:#fff}
.page-links span{font-size:17px;font-weight:400}
.page-links a:focus-visible{outline:3px solid #9ec7b6;outline-offset:2px}
.subject-section{border-top:1px solid #dfe9e1;padding-top:18px;margin-top:18px}
.menu-note{font-size:11px;line-height:1.8;color:#76887c;margin:20px 10px 4px}
@container(min-width:230px){
  .page-links{grid-template-columns:repeat(2,minmax(0,1fr))}
  .subject-section{margin-top:12px;padding-top:12px}
  .menu-note{display:none}
}
</style>
