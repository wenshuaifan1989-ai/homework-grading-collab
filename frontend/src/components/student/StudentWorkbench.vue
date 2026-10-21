<template>
  <div class="workbench">
    <div class="work-area"><slot /></div>
    <aside class="reminders" aria-label="学习提醒"><slot name="reminders" /></aside>
  </div>
</template>
<style scoped>
.workbench{display:grid;grid-template-columns:minmax(0,1fr) 256px;gap:22px;align-items:start;width:100%;max-width:1420px;margin:0 auto}.work-area{min-width:0}.reminders{display:grid;gap:16px;position:sticky;top:24px;min-width:0}@media(max-width:1150px){.workbench{grid-template-columns:minmax(0,1fr)}.reminders{position:static;grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr))}}
</style>
