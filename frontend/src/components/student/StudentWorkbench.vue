<script setup lang="ts">
import { ref } from 'vue'
const remindersExpanded = ref(false)
</script>
<template>
  <div class="workbench">
    <div class="workbench-grid">
      <aside class="study-navigation" aria-label="学生学习导航"><slot name="navigation" /></aside>
      <div class="work-area"><slot /></div>
      <aside class="reminders" :class="{ expanded: remindersExpanded }" aria-label="学习提醒">
        <button type="button" class="reminder-toggle" :aria-expanded="remindersExpanded" @click="remindersExpanded = !remindersExpanded">
          <span>学习提醒与待办</span><span>{{ remindersExpanded ? '收起 −' : '展开 +' }}</span>
        </button>
        <div class="reminder-content"><slot name="reminders" /></div>
      </aside>
    </div>
  </div>
</template>
<style scoped>
.workbench{container-type:inline-size;width:100%;min-width:0;margin:0 auto}
.workbench-grid{display:grid;grid-template-columns:144px minmax(0,1fr) 210px;grid-template-areas:"navigation work reminders";gap:16px;align-items:start}
.study-navigation,.reminders{position:sticky;top:20px;min-width:0}
.study-navigation{grid-area:navigation}
.reminders{grid-area:reminders}
.reminder-content{display:grid;gap:14px}
.reminder-toggle{display:none}
.work-area{grid-area:work}
.work-area{min-width:0;overflow-wrap:anywhere}
@container(max-width:850px){
  .workbench-grid{grid-template-columns:144px minmax(0,1fr);grid-template-areas:"navigation reminders" "navigation work"}
  .reminders{position:static}
  .reminder-toggle{display:flex;width:100%;justify-content:space-between;gap:12px;align-items:center;min-height:42px;padding:10px 14px;font:inherit;font-size:13px;background:#edf5ef;border:1px solid #d8e5dc;border-radius:10px;color:#365d49;cursor:pointer}
  .reminder-toggle:focus-visible{outline:3px solid #9ec7b6;outline-offset:2px}
  .reminder-content{display:none;margin-top:12px;grid-template-columns:repeat(auto-fit,minmax(min(100%,200px),1fr))}
  .expanded .reminder-content{display:grid}
}
@container(max-width:580px){
  .workbench-grid{grid-template-columns:minmax(0,1fr);grid-template-areas:"navigation" "reminders" "work";gap:12px}
  .study-navigation{position:static}
}
</style>
