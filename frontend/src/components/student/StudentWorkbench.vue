<script setup lang="ts">
import { ref } from 'vue'
const remindersExpanded = ref(false)
</script>
<template>
  <div class="workbench">
    <div v-if="$slots.navigation" class="subject-toolbar"><slot name="navigation" /></div>
    <div class="workbench-grid" :class="{ 'with-reminders': !!$slots.reminders }">
      <div class="work-area"><slot /></div>
      <aside v-if="$slots.reminders" class="reminders" :class="{ expanded: remindersExpanded }" aria-label="学习提醒">
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
.subject-toolbar{margin-bottom:16px;min-width:0}
.workbench-grid{display:grid;grid-template-columns:minmax(0,1fr);gap:20px;align-items:start}
.workbench-grid.with-reminders{grid-template-columns:minmax(0,1fr) 220px}
.reminders{position:sticky;top:20px;min-width:0}
.reminder-content{display:grid;gap:14px}
.reminder-toggle{display:none}
.work-area{min-width:0;overflow-wrap:anywhere}
@container(max-width:850px){
  .workbench-grid,.workbench-grid.with-reminders{grid-template-columns:minmax(0,1fr);gap:14px}
  .reminders{position:static}
  .reminder-toggle{display:flex;width:100%;justify-content:space-between;gap:12px;align-items:center;min-height:42px;padding:10px 14px;font:inherit;font-size:13px;background:#edf5ef;border:1px solid #d8e5dc;border-radius:10px;color:#365d49;cursor:pointer}
  .reminder-toggle:focus-visible{outline:3px solid #9ec7b6;outline-offset:2px}
  .reminder-content{display:none;margin-top:12px;grid-template-columns:repeat(auto-fit,minmax(min(100%,200px),1fr))}
  .expanded .reminder-content{display:grid}
}
@container(max-width:580px){
  .workbench-grid{gap:12px}
  .reminder-toggle{min-height:44px;font-size:14px}
}
</style>
