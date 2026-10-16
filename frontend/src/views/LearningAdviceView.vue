<script setup lang="ts">
import { ref,onMounted,onBeforeUnmount } from 'vue'
import client from '@/api/client'
import { teacherApi } from '@/api/teacher'
const props=defineProps<{initialClassId?:number;initialSubject?:string;initialStudentIds?:number[]}>()
const classes=ref<any[]>([]),classId=ref(0),subject=ref('math'),data=ref<any>(null),selected=ref<number[]>([])
const busy=ref(false),error=ref(''),notice=ref(''),levels=ref<Record<number,string>>({}),reasons=ref<Record<number,string>>({})
const count=ref(1),difficulty=ref('mixed'),type=ref(''),assetInput=ref(''),feedback=ref<any>(null),bank=ref<any[]>([])
const reviewCandidates=ref<any[]>([]),reviewReasons=ref<Record<number,string>>({}),reviewImage=ref('')
const subjects=[['math','数学'],['physics','物理'],['chemistry','化学']]
async function run(action:()=>Promise<void>){if(busy.value)return;busy.value=true;error.value='';notice.value='';try{await action()}catch(e:any){const d=e.response?.data?.detail;error.value=typeof d==='string'?d:d?.message||JSON.stringify(d)||e.message}finally{busy.value=false}}
async function load(){reviewCandidates.value=[];if(reviewImage.value)URL.revokeObjectURL(reviewImage.value);reviewImage.value='';data.value=(await client.get(`/learning-advice/classes/${classId.value}/${subject.value}`)).data;selected.value=(props.initialStudentIds||[]).filter(id=>data.value.students.some((s:any)=>s.student_id===id));feedback.value=null;bank.value=[]}
async function generate(){if(!selected.value.length)throw Error('请先选择学生');await client.post(`/learning-advice/classes/${classId.value}/${subject.value}/suggestions`,{student_ids:selected.value});await load();notice.value='规则辅助建议已生成；档位没有自动改变。'}
async function decision(s:any,action:string){if(!reasons.value[s.id])throw Error('请填写教师审阅或调整原因');await client.post(`/learning-advice/suggestions/${s.id}/decision`,{action,target_level:action==='REJECT'?null:levels.value[s.id]||s.proposed_level,expected_level:s.current_level,reason:reasons.value[s.id],request_key:crypto.randomUUID()});await load();notice.value=action==='REJECT'?'已拒绝，档位未改变。':'教师决定已记录，可再次明确调整以撤销之前的变档；审计保留。'}
function ids(){return assetInput.value.trim()?assetInput.value.split(/[,，\s]+/).map(Number):null}
async function candidates(){const grade=classes.value.find(c=>c.id===classId.value)?.grade||'grade7';bank.value=(await client.get('/assignment-plans/question-bank/search',{params:{class_id:classId.value,subject:subject.value,grade}})).data.data.items.filter((q:any)=>q.review_status==='CONFIRMED')}
async function practice(){if(!selected.value.length)throw Error('请先选择目标学生');await client.post(`/learning-advice/classes/${classId.value}/${subject.value}/practices`,{student_ids:selected.value,count:count.value,difficulty:difficulty.value,question_type:type.value||null,selected_asset_ids:ids(),request_key:crypto.randomUUID()});await load();notice.value='专项草稿已保存，尚未发布。请逐题核对题干、答案、解析及实际目标学生。'}
async function replace(p:any){const chosen=ids();if(!chosen)throw Error('请在选题ID框填写替换的完整三版本题目ID');await client.put(`/learning-advice/practices/${p.id}/questions`,{asset_ids:chosen});await load();notice.value='草稿已换题，仍须教师核对确认。'}
async function confirm(p:any){if(!window.confirm(`确认已逐题核对答案解析，并确认目标学生ID为 ${p.student_ids.join('、')}？`))return;await client.post(`/learning-advice/practices/${p.id}/confirm`,{confirmed:true});await load();notice.value='已确认；还未发布，学生暂不可见。'}
async function publish(p:any){if(!window.confirm(`只向目标学生 ${p.student_ids.join('、')} 发布此专项训练？`))return;await client.post(`/learning-advice/practices/${p.id}/publish`,{confirmed:true});await load();notice.value='已按目标学生发布；沿用原作业提交与复核流程。'}
async function results(p:any){feedback.value=(await client.get(`/learning-advice/practices/${p.id}/feedback`)).data}
async function candidatesForReview(){reviewCandidates.value=(await client.get(`/learning-advice/classes/${classId.value}/${subject.value}/review-candidates`)).data.items}
async function sourceImage(r:any){if(reviewImage.value)URL.revokeObjectURL(reviewImage.value);const response=await client.get(`/paper/sources/${r.source_id}/image`,{responseType:'blob'});reviewImage.value=URL.createObjectURL(response.data)}
async function evidenceReview(r:any,confirmed:boolean){if(!reviewReasons.value[r.grade_id])throw Error('请填写核对依据');await client.post(`/learning-advice/grades/${r.grade_id}/evidence-review`,{confirmed,expected_version:r.version,reason:reviewReasons.value[r.grade_id],request_key:crypto.randomUUID()});await load();await candidatesForReview();notice.value='可信评分复核已记录；没有修改原分数。建议须重新生成审阅。'}
async function print(p:any,level:string){const path=p.status==='PUBLISHED'?`/learning/assignments/${p.assignment_id}/variants/${level}/print.pdf`:`/assignment-plans/${p.plan.id}/variants/${level}/print.pdf`;const response=await client.get(path,{responseType:'blob'});const url=URL.createObjectURL(response.data);const link=document.createElement('a');link.href=url;link.download='专项训练.pdf';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
onMounted(()=>run(async()=>{classes.value=await teacherApi.classes();if(classes.value.length){classId.value=props.initialClassId||classes.value[0].id;subject.value=props.initialSubject||subject.value;await load()}}))
onBeforeUnmount(()=>{if(reviewImage.value)URL.revokeObjectURL(reviewImage.value)})
</script>
<template>
 <section class="advice">
  <h1>学科建议与专项训练</h1><p>RULE_ASSISTED · MODEL_NOT_RUN：AI未运行，待授权。下方是透明规则线索，不是能力诊断；提交率、拍照习惯和交作业快慢均不参与判断。</p>
  <p role="alert" class="error">{{ error }}</p><p role="status">{{ notice }}</p>
  <select v-model="classId" @change="run(load)" aria-label="班级"><option v-for="c in classes" :key="c.id" :value="c.id">{{ c.name }}</option></select>
  <select v-model="subject" @change="run(load)" aria-label="学科"><option v-for="s in subjects" :key="s[0]" :value="s[0]">{{ s[1] }}</option></select>
  <button :disabled="busy||!classId" @click="run(load)">刷新已确认学情</button>
  <router-link to="/teacher/learning">原手动分层</router-link> · <router-link to="/teacher/assignment-plans">原题库与作业助手</router-link>
  <template v-if="data">
   <details><summary>已有非括号作业：人工核对评分是否可作为学情证据</summary><p>题目资产审核不等于评分审核。这里仅确认/撤销已有评分的可信性，不改分；013_V01括号任务必须在原括号复核入口处理。</p><button :disabled="busy" @click="run(candidatesForReview)">读取已完成作业的评分核对列表</button><img v-if="reviewImage" :src="reviewImage" alt="教师核对原题裁切" style="max-width:100%;max-height:500px"/><article v-for="r in reviewCandidates" :key="r.grade_id" class="source"><p>学生{{ r.student_id }} · {{ r.task_id }} · {{ r.question_text }} · {{ r.score }}/{{ r.max_score }} · {{ r.result }} · 标准答案{{ r.answer }} · 已确认{{ r.reviewed }}</p><button :disabled="busy" @click="run(()=>sourceImage(r))">查看原题裁切再核对</button><input v-model="reviewReasons[r.grade_id]" placeholder="核对依据"/><button :disabled="busy||r.reviewed" @click="run(()=>evidenceReview(r,true))">确认已有评分可信（不改分）</button><button :disabled="busy||!r.reviewed" @click="run(()=>evidenceReview(r,false))">撤销可信确认</button></article></details>
   <p>试点门槛：至少2份独立作业、6道不重复原题、2个知识点；不是科研结论。不同难度分开看，不以粗正确率直接推档。</p>
   <button :disabled="busy||!selected.length" @click="run(generate)">为已选学生生成待审阅建议（不会变档）</button>
   <article v-for="student in data.students" :key="student.student_id" class="card">
    <h2><input v-model="selected" type="checkbox" :value="student.student_id" :aria-label="'选择'+student.name"/>{{ student.name }} · 学生ID {{ student.student_id }}</h2>
    <p>教师可见当前档位：{{ student.current_level||'未设定' }} · {{ student.summary.evidence_status }} · {{ student.summary.task_count }}份独立作业 / {{ student.summary.unique_question_count }}道不重复原题</p>
    <details><summary>展开可信证据与知识点/难度</summary><pre>{{ student.summary.knowledge_points }}</pre>
     <div v-for="source in student.summary.sources" :key="source.grade_id" class="source"><p>{{ source.task_id }} / 第{{ source.question_no }}题 / 资产{{ source.asset_id }} / 教师{{ source.reviewer_id }} / {{ source.confirmed_at }}</p><p>{{ source.question_text }}</p><p>{{ source.score }}/{{ source.max_score }} · {{ source.difficulty }} · {{ source.outcome }} · {{ source.knowledge_points.join('、') }}</p><pre v-if="source.mistake">{{ source.mistake }}</pre></div>
    </details>
    <div v-for="suggestion in student.suggestions" :key="suggestion.id" class="suggestion">
     <h3>建议 #{{ suggestion.id }} · {{ suggestion.status }}</h3><p>{{ suggestion.rationale.reason }}</p><p>候选档位：{{ suggestion.proposed_level||'证据不足，不建议档位' }}；薄弱知识点：{{ suggestion.rationale.weak_knowledge_points.join('、')||'暂无可信错题信号' }}</p>
     <small>证据版本 {{ suggestion.evidence_hash }}</small>
     <select v-model="levels[suggestion.id]" aria-label="教师选择档位"><option value="">沿用建议档位</option><option>L1</option><option>L2</option><option>L3</option></select>
     <input v-model="reasons[suggestion.id]" placeholder="教师审阅/拒绝/再次调整原因（必填）" aria-label="审阅原因"/>
     <button :disabled="busy||suggestion.status!=='REVIEW_PENDING'" @click="run(()=>decision(suggestion,'ACCEPT'))">教师确认后生效</button>
     <button :disabled="busy||!['REVIEW_PENDING','NEEDS_MORE_EVIDENCE'].includes(suggestion.status)" @click="run(()=>decision(suggestion,'REJECT'))">拒绝，不改档</button>
     <button :disabled="busy||suggestion.status!=='ACCEPTED'" @click="run(()=>decision(suggestion,'ADJUST'))">明确再次调整 / 撤销上次变档</button>
     <details><summary>查看决定审计</summary><pre>{{ suggestion.history }}</pre></details>
    </div>
   </article>
   <h2>从已确认薄弱知识点创建专项训练</h2><p>当前选中学生ID：{{ selected.join('、')||'未选择' }}。每版本题数和难度由教师设置；必须有足够已审核且不是原题的合法题目。学生只收到“专项训练”，不见档位与建议理由。</p>
   <label>每版本题数<input v-model.number="count" type="number" min="1" max="20"/></label><select v-model="difficulty" aria-label="训练难度"><option value="mixed">混合难度</option><option value="easy">基础难度</option><option value="medium">中等难度</option><option value="hard">挑战难度</option></select>
   <input v-model="type" placeholder="题型（可选）"/><button :disabled="busy" @click="run(candidates)">查看已审核题库（教师自行选/替换）</button>
   <details v-if="bank.length" open><summary>题库内容（后端仍会排除原题、错知识点等不合规选项）</summary><article v-for="q in bank" :key="q.id" class="source"><b>ID {{ q.id }} · {{ q.difficulty }}</b><p>{{ q.question_text }}</p><p>答案：{{ q.correct_answer }}；解析：{{ q.analysis }}；来源：{{ q.rights_reference }}</p></article></details>
   <input v-model="assetInput" class="ids" placeholder="可选：按三个版本顺序填写3×题数个不同题目ID，逗号分隔；留空按规则检索" aria-label="自选或替换题目ID"/>
   <button :disabled="busy||!selected.length" @click="run(practice)">生成可审阅专项草稿</button>
   <article v-for="p in data.practices" :key="p.id" class="card"><h3>专项 #{{ p.id }} · {{ p.status }}</h3><p>目标学生ID：{{ p.student_ids.join('、') }} · 知识点：{{ p.knowledge_points.join('、') }}</p>
    <div v-for="v in p.plan?.variants" :key="v.level"><h4>{{ v.level }}（仅教师可见）</h4><button :disabled="busy" @click="run(()=>print(p,v.level))">{{ p.status==='PUBLISHED'?'下载正式卷（选择题同时注册括号模板）':'预览草稿PDF（不是正式拍照模板）' }}</button><div v-for="q in v.questions" :key="q.id" class="source"><p>{{ q.question_text }}</p><p>标准答案：{{ q.correct_answer }}</p><p>解析：{{ q.analysis }}</p><p>来源：{{ q.rights_reference }}</p></div></div>
    <button :disabled="busy||p.status!=='DRAFT'" @click="run(()=>replace(p))">按上方ID替换草稿题目</button><button :disabled="busy||p.status!=='DRAFT'" @click="run(()=>confirm(p))">逐题核对后确认</button><button :disabled="busy||p.status!=='CONFIRMED'" @click="run(()=>publish(p))">确认目标学生并发布</button><button :disabled="busy||p.status!=='PUBLISHED'" @click="run(()=>results(p))">查看训练结果回流</button>
   </article>
   <details v-if="feedback" open><summary>已确认训练结果与更新后同科学情</summary><pre>{{ feedback }}</pre></details>
  </template>
 </section>
</template>
<style scoped>.advice{padding:24px;max-width:1200px;margin:auto}.card{border:1px solid #cbd5e1;padding:18px;border-radius:10px;margin:16px 0}.source,.suggestion{padding:12px;border-left:3px solid #94a3b8;margin:10px 0;background:#f8fafc}input,select,button{padding:8px;margin:5px;max-width:100%}.ids{width:90%}.error{color:#b91c1c}pre,small{white-space:pre-wrap;overflow-wrap:anywhere}button:disabled{opacity:.5}</style>
