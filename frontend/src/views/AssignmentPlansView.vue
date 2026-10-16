<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { assignmentPlansApi, type AssignmentPlan, type QuestionBankItem } from '@/api/assignmentPlans'
import { teacherApi, type Classroom } from '@/api/teacher'
const classes=ref<Classroom[]>([]), classId=ref(0), subject=ref('math'), grade=ref('grade9')
const query=ref(''), difficulty=ref(''), items=ref<QuestionBankItem[]>([]), plans=ref<AssignmentPlan[]>([])
const selectedPlan=ref<AssignmentPlan|null>(null), error=ref(''), busy=ref(false)
const ai=ref<{message:string;daily_request_limit:number}|null>(null)
async function run(fn:()=>Promise<void>){if(busy.value)return;busy.value=true;error.value='';try{await fn()}catch(e:any){const d=e.response?.data?.detail;error.value=typeof d==='string'?d:e.message||'加载失败'}finally{busy.value=false}}
async function search(){if(!classId.value)throw Error('请选择班级');items.value=(await assignmentPlansApi.search(classId.value,subject.value,grade.value,query.value,difficulty.value)).items}
onMounted(()=>run(async()=>{const [c,p,a]=await Promise.all([teacherApi.classes(),assignmentPlansApi.list(),assignmentPlansApi.aiStatus()]);classes.value=c;classId.value=c[0]?.id||0;plans.value=p;ai.value=a}))
</script>
<template>
 <section aria-label="题库助手">
  <h3>教师题目检索</h3><p v-if="error" role="alert">{{ error }}</p>
  <label>检索班级<select v-model="classId"><option v-for="c in classes" :key="c.id" :value="c.id">{{ c.name }}</option></select></label>
  <label>检索学科<select v-model="subject"><option value="math">数学</option><option value="physics">物理</option><option value="chemistry">化学</option></select></label>
  <label>检索年级<select v-model="grade"><option value="grade7">七年级</option><option value="grade8">八年级</option><option value="grade9">九年级</option></select></label>
  <label>题干或知识点<input v-model="query" /></label><label>检索难度<select v-model="difficulty"><option value="">全部</option><option value="easy">基础</option><option value="medium">中等</option><option value="hard">挑战</option></select></label>
  <button :disabled="busy||!classId" @click="run(search)">搜索审核题目</button>
  <article v-for="q in items" :key="q.id"><h4>题目{{ q.id }}</h4><p>{{ q.question_text }}</p><p>知识点：{{ q.knowledge_points.join('、') }} · 来源：{{ q.rights_basis }}</p><details><summary>教师查看答案与解析</summary><p>{{ q.correct_answer }} · {{ q.analysis }}</p></details></article>
  <h3>和AI说想法</h3><p>{{ ai?.message||'正在检查模型权限' }} · 当前额度{{ ai?.daily_request_limit??0 }}。本轮未授权收费调用，因此不显示无法执行的生成按钮。</p><p>自主选题：在上方套卷库展开原卷，选择“选用已审核题目”关联后整套确认，再到作业管理统一发布。专项训练由可信作业看板发起。</p>
  <h3>已有作业计划（只读）</h3><button v-for="p in plans" :key="p.id" :disabled="busy" @click="run(async()=>{selectedPlan=await assignmentPlansApi.get(p.id)})">{{ p.title }} · {{ p.status }}</button><p v-if="!plans.length">暂无已有计划。</p>
  <article v-if="selectedPlan"><h4>{{ selectedPlan.title }} · 原发布{{ selectedPlan.assignment_id||'未发布' }}</h4><section v-for="v in selectedPlan.variants" :key="v.level"><h4>原{{ v.level }}版本</h4><ol><li v-for="q in v.questions" :key="q.source_asset_id">{{ q.question_text }}<p>答案：{{ q.correct_answer }} · {{ q.analysis }}</p></li></ol></section></article>
 </section>
</template>
<style scoped>
label{display:inline-block;margin:8px}input,select,button{font:inherit;padding:8px;border:1px solid #bdcbe0;border-radius:6px}label>input,label>select{display:block;margin-top:4px}button{margin:6px;background:#edf3ff;color:#1d4ed8}article{padding:12px;margin:10px 0;border:1px solid #e4eaf4;border-radius:8px}
</style>
