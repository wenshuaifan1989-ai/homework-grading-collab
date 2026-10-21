<template>
  <div class="workbench">
    <div class="workbench-grid">
      <aside class="study-navigation" aria-label="学生学习导航"><slot name="navigation" /></aside>
      <div class="work-area"><slot /></div>
      <aside class="reminders" aria-label="学习提醒"><slot name="reminders" /></aside>
    </div>
  </div>
</template>
<style scoped>
.workbench{container-type:inline-size;width:100%;min-width:0;margin:0 auto}
.workbench-grid{display:grid;grid-template-columns:154px minmax(0,1fr) 210px;gap:18px;align-items:start}
.study-navigation,.reminders{position:sticky;top:24px;min-width:0}
.work-area{min-width:0;overflow-wrap:anywhere}
.reminders{display:grid;gap:16px}
@container(max-width:850px){
  .workbench-grid{grid-template-columns:154px minmax(0,1fr)}
  .reminders{position:static;grid-column:2;grid-template-columns:repeat(auto-fit,minmax(min(100%,210px),1fr))}
}
@container(max-width:580px){
  .workbench-grid{grid-template-columns:minmax(0,1fr);gap:16px}
  .study-navigation{position:static}
  .reminders{grid-column:1}
}
</style>
