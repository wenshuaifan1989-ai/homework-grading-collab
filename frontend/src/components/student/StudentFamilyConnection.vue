<script setup lang="ts">
defineProps<{ canInvite: boolean; busy: boolean; inviteCode: string }>()
const code = defineModel<string>('code', { required: true })
const relationship = defineModel<string>('relationship', { required: true })
defineEmits<{ create: []; claim: [] }>()
</script>
<template>
  <details class="family-panel">
    <summary>家庭关联</summary>
    <p>只向实际家庭成员提供一次性关系码。</p>
    <div v-if="canInvite" class="family-fields">
      <button type="button" :disabled="busy" @click="$emit('create')">生成家庭成员邀请</button>
      <code v-if="inviteCode">{{ inviteCode }}</code>
    </div>
    <form class="family-fields" @submit.prevent="$emit('claim')">
      <label>家庭关系码<input v-model="code" maxlength="32" autocomplete="off" /></label>
      <label>与学生的关系<select v-model="relationship">
        <option value="father">父亲</option><option value="mother">母亲</option><option value="guardian">监护人</option>
        <option value="paternal_grandfather">祖父</option><option value="paternal_grandmother">祖母</option>
        <option value="maternal_grandfather">外祖父</option><option value="maternal_grandmother">外祖母</option><option value="other">其他</option>
      </select></label>
      <button type="submit" :disabled="busy || !code.trim()">确认家庭关联</button>
    </form>
  </details>
</template>
<style scoped>
.family-panel{margin-top:12px;border:1px solid #dde6db;padding:11px;border-radius:10px;background:#fafcf8;font-size:12px;color:#63806a;min-width:0}
summary{cursor:pointer;line-height:1.8}
p{font-size:11px;color:#7b8b80;line-height:1.8}
.family-fields{display:grid;gap:10px;margin-top:12px;min-width:0}
label{display:grid;gap:7px;font-size:12px;min-width:0}
input,select,button{box-sizing:border-box;width:100%;max-width:100%;min-width:0;font:inherit;font-size:12px;border:1px solid #d3dfd7;border-radius:8px;padding:8px;background:#fff;color:#365d49}
button{cursor:pointer;line-height:1.7}
button:disabled{opacity:.45;cursor:not-allowed}
input:focus-visible,select:focus-visible,button:focus-visible,summary:focus-visible{outline:3px solid #9ec7b6;outline-offset:2px}
code{color:#41624c;overflow-wrap:anywhere;font-size:11px}
</style>
