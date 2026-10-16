<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import client from '@/api/client'
import { teacherApi } from '@/api/teacher'
const props=defineProps<{initialClassId?:number;initialAssignmentId?:number}>()

const classes=ref<any[]>([]), assignments=ref<any[]>([]), classId=ref(0), assignmentId=ref(0)
const variants=ref<any[]>([]), tasks=ref<any[]>([]), variant=ref<any>(null), page=ref<any>(null), detail=ref<any>(null)
const message=ref(''), busy=ref(false), pageUrl=ref(''), evidence=ref<Record<string,string>>({})
const blankReferenceConfirmed=ref(false)
const registrations=ref<Record<number,{page_id:number,original:string,reference:string,note:string,regions:string}>>({})
const mapping=ref<any[]>([]), selected=ref(0), boxKind=ref('answer_bracket_bbox'), canvas=ref<HTMLCanvasElement|null>(null)
const mappingInput=ref('')
function loadMappingDraft(){const rows=JSON.parse(mappingInput.value);if(!Array.isArray(rows)||!rows.length||rows.length>100)throw Error('需要本页1至100题位置JSON');mapping.value=rows.map((p:any)=>{const q=variant.value.questions.find((q:any)=>String(q.number)===String(p.question_number));if(!q)throw Error('题号不属于当前原卷');return {variant_question_id:q.id,question_number:String(q.number),stem_bbox:p.stem_bbox,answer_bracket_bbox:p.answer_bracket_bbox,options_bbox:p.options_bbox,question_bbox:p.question_bbox,choice_kind:p.choice_kind||'single'}});blankReferenceConfirmed.value=false;draw()}
const relocation=ref<Record<number,string>>({}), decisions=ref<Record<number,string>>({}), notes=ref<Record<number,string>>({})
const urls:string[]=[]
async function run(action:()=>Promise<void>) { if(busy.value)return;busy.value=true;message.value='';try{await action()}catch(e:any){message.value=e.response?.data?.detail||e.message}finally{busy.value=false} }
async function fileUrl(path:string) { const r=await client.get(path,{responseType:'blob'});const u=URL.createObjectURL(r.data);urls.push(u);return u }
async function loadAssignments(){assignments.value=await teacherApi.assignments(classId.value);variants.value=[];page.value=null}
async function load(){const r=await client.get(`/known-assignments/assignments/${assignmentId.value}`);variants.value=r.data.variants;tasks.value=r.data.tasks;variant.value=variants.value.find(v=>v.id===variant.value?.id)||variants.value[0];page.value=null}
async function choosePage(p:any){page.value=p;mapping.value=JSON.parse(JSON.stringify(p.placements));pageUrl.value=await fileUrl(`/known-assignments/pages/${p.id}/file`);const img=new Image();img.onload=()=>{if(canvas.value){canvas.value.width=p.width;canvas.value.height=p.height;canvas.value.getContext('2d')!.drawImage(img,0,0);draw()}};img.src=pageUrl.value}
function add(){const q=variant.value.questions.find((q:any)=>!mapping.value.some(p=>p.variant_question_id===q.id));if(!q)return;mapping.value.push({variant_question_id:q.id,question_number:String(q.number),stem_bbox:[0,0,100,50],answer_bracket_bbox:[20,10,80,40],options_bbox:[0,60,100,140],question_bbox:[0,0,100,150],choice_kind:'single'});selected.value=mapping.value.length-1;draw()}
function draw(){if(!canvas.value||!page.value)return;const img=new Image();img.onload=()=>{const ctx=canvas.value!.getContext('2d')!;ctx.drawImage(img,0,0);mapping.value.forEach((p:any,i:number)=>{ctx.strokeStyle=i===selected.value?'#ef4444':'#2563eb';ctx.lineWidth=3;for(const k of ['stem_bbox','answer_bracket_bbox','options_bbox','question_bbox']){const b=p[k];ctx.strokeRect(b[0],b[1],b[2]-b[0],b[3]-b[1])}ctx.fillStyle='#b91c1c';ctx.font='20px sans-serif';ctx.fillText(p.question_number,p.stem_bbox[0],Math.max(20,p.stem_bbox[1]))})};img.src=pageUrl.value}
let start:number[]|null=null
function point(e:PointerEvent){const r=canvas.value!.getBoundingClientRect();return [Math.round((e.clientX-r.left)*page.value.width/r.width),Math.round((e.clientY-r.top)*page.value.height/r.height)]}
function down(e:PointerEvent){if(page.value?.status!=='DRAFT'||!mapping.value[selected.value])return;start=point(e);canvas.value!.setPointerCapture(e.pointerId)}
function up(e:PointerEvent){if(!start)return;const end=point(e);mapping.value[selected.value][boxKind.value]=[Math.min(start[0],end[0]),Math.min(start[1],end[1]),Math.max(start[0],end[0]),Math.max(start[1],end[1])];start=null;draw()}
async function generate(){await client.post(`/known-assignments/variants/${variant.value.id}/generate`);await load();message.value='已注册标准PDF、页模板和题干括号坐标。'}
async function upload(e:Event){const f=(e.target as HTMLInputElement).files?.[0];if(!f)return;await run(async()=>{const data=new FormData();data.append('file',f);await client.post(`/known-assignments/variants/${variant.value.id}/upload`,data);await load();message.value='上传已保存为草稿，请逐页标定后激活。'})}
async function save(){if(!blankReferenceConfirmed.value)throw Error('请先确认括号内无标准答案或学生笔迹');await client.put(`/known-assignments/pages/${page.value.id}/mapping`,{placements:mapping.value,blank_reference_confirmed:true});message.value='本页标定已保存，请完整标定全部页面后激活。'}
async function activate(){await client.post(`/known-assignments/pages/${page.value.id}/activate-set`);await load();message.value='模板已激活，学生沿用原有提交入口。'}
async function pdf(){const url=await fileUrl(`/known-assignments/pages/${page.value.id}/file?kind=pdf`);const a=document.createElement('a');a.href=url;a.download='已知作业.pdf';a.click()}
async function task(id:string){detail.value=(await client.get(`/known-assignments/tasks/${id}`)).data;const next:Record<string,string>={};for(const p of detail.value.pages){next[`original-${p.id}`]=await fileUrl(`/known-assignments/tasks/${id}/images/${p.id}`);if(p.status==='MATCHED')next[`aligned-${p.id}`]=await fileUrl(`/known-assignments/tasks/${id}/images/${p.id}?kind=aligned`)}for(const r of detail.value.reads){next[`crop-${r.id}`]=await fileUrl(`/known-assignments/tasks/${id}/images/${r.id}?kind=crop`);next[`ink-${r.id}`]=await fileUrl(`/known-assignments/tasks/${id}/images/${r.id}?kind=ink`);next[`template-${r.id}`]=await fileUrl(`/known-assignments/pages/${r.page_id}/file`);decisions.value[r.id]=['A','B','C','D','BLANK'].includes(r.symbol)?r.symbol:'';relocation.value[r.id]=r.bbox.join(',')}evidence.value=next}
async function confirm(r:any){if(!decisions.value[r.id]||!notes.value[r.id])throw Error('请核对裁切图、填写字母及复核说明');await client.post(`/known-assignments/tasks/${detail.value.task_id}/reads/${r.id}/review`,{symbol:decisions.value[r.id].toUpperCase(),note:notes.value[r.id],request_key:crypto.randomUUID()});await task(detail.value.task_id)}
async function relocate(r:any){if(!notes.value[r.id])throw Error('请填写重定位原因');await client.post(`/known-assignments/tasks/${detail.value.task_id}/reads/${r.id}/relocate`,{bbox:relocation.value[r.id].split(',').map(Number),note:notes.value[r.id],request_key:crypto.randomUUID()});await task(detail.value.task_id)}
function registration(id:number){return registrations.value[id] ||= {page_id:0,original:'',reference:'',note:'',regions:''}}
async function registerPage(p:any){const v=registration(p.id);const ref=detail.value.allowed_pages.find((x:any)=>x.id===v.page_id);if(!ref)throw Error('请选择当前学生版本的参考页');await client.post(`/known-assignments/tasks/${detail.value.task_id}/pages/${p.id}/register`,{page_id:ref.id,expected_template_sha256:ref.image_sha256,original_points:JSON.parse(v.original||'[]'),reference_points:JSON.parse(v.reference||'[]'),question_regions:v.regions.trim()?JSON.parse(v.regions):null,note:v.note,request_key:crypto.randomUUID()});await task(detail.value.task_id)}
async function showReference(id:number){evidence.value[`registration-reference-${id}`]=await fileUrl(`/known-assignments/pages/${id}/file`)}
async function recover(){const r=(await client.post(`/known-assignments/tasks/${detail.value.task_id}/recover`)).data;await task(detail.value.task_id);message.value=`本地安全恢复${r.recovered_pages}页，${r.status}；仍不确定的页与答案保持人工核对，不收费。`}
onMounted(()=>run(async()=>{classes.value=await teacherApi.classes();if(classes.value.length){classId.value=props.initialClassId||classes.value[0].id;await loadAssignments();if(props.initialAssignmentId){assignmentId.value=props.initialAssignmentId;await load()}}}))
onBeforeUnmount(()=>urls.forEach(u=>URL.revokeObjectURL(u)))
watch(variant,()=>{page.value=null;mapping.value=[];blankReferenceConfirmed.value=false})
watch(page,()=>{blankReferenceConfirmed.value=false})
</script>

<template>
  <section class="known">
    <h1>已知作业 · 题干括号答案</h1>
    <p>只识别题干末尾括号里的手写字母，四个印刷选项在其下方。不调用付费模型。当前笔迹候选须教师复核后才记分。</p>
    <p role="status">{{ message }}</p>
    <select v-model="classId" :disabled="busy" @change="run(loadAssignments)"><option v-for="c in classes" :key="c.id" :value="c.id">{{ c.name }}</option></select>
    <select v-model="assignmentId" :disabled="busy" @change="run(load)"><option :value="0">选择作业</option><option v-for="a in assignments" :key="a.id" :value="a.id">{{ a.title }}</option></select>
    <button :disabled="busy||!assignmentId" @click="run(load)">刷新</button>
    <div v-if="variants.length">
      <select v-model="variant" :disabled="busy"><option v-for="v in variants" :key="v.id" :value="v">{{ v.level }}（仅教师可见）</option></select>
      <button :disabled="busy" @click="run(generate)">生成并注册标准PDF</button>
      <label>或上传已知卷 PDF/图片<input type="file" accept="application/pdf,image/*" :disabled="busy" @change="upload" /></label>
      <p>上传卷按既有题库顺序关联，答案不必重录。已激活版本不可原地覆盖；重新上传产生新版本，已有学生提交时需新建作业版本。</p>
      <button v-for="p in variant?.pages" :key="p.id" @click="run(()=>choosePage(p))">v{{ p.export_version }} 第{{ p.page_index+1 }}页 {{ p.status }}</button>
    </div>
    <div v-if="page" class="mapping">
      <div><h2>本页标定（左上角原图像素坐标）</h2>
        <button v-if="page.has_pdf" @click="run(pdf)">下载PDF</button>
        <button v-if="page.status==='DRAFT'" @click="add">添加本页题目</button>
        <select v-model="selected" @change="draw"><option v-for="(p,i) in mapping" :key="i" :value="i">第{{ p.question_number }}题</option></select>
        <select v-model="boxKind"><option value="stem_bbox">题干范围</option><option value="answer_bracket_bbox">题干末括号</option><option value="options_bbox">四个选项范围</option><option value="question_bbox">整题范围</option></select>
        <p>选中范围类型后，在右侧原页拖框；括号必须在题干内、位于选项之前。</p>
        <details v-if="page.status==='DRAFT'"><summary>载入已有人工标定（位置JSON，不含学生答案）</summary><p>仅限当前同一原页的已核对坐标；载入不会保存或激活，仍须查看原图并确认空白参考，服务端继续校验范围、题号及版本。</p><textarea v-model="mappingInput" aria-label="本页人工位置JSON"/><button :disabled="busy" @click="run(async()=>loadMappingDraft())">载入人工标定草稿</button></details>
        <div v-for="(p,i) in mapping" :key="i" class="card">
          <select v-model="p.variant_question_id" :disabled="page.status!=='DRAFT'"><option v-for="q in variant.questions" :key="q.id" :value="q.id">{{ q.number }}. {{ q.text.slice(0,45) }}</option></select>
          <input v-model="p.question_number" aria-label="题号" :disabled="page.status!=='DRAFT'" />
          <select v-model="p.choice_kind" :disabled="page.status!=='DRAFT'"><option value="single">单选</option><option value="multi">多选（全对得分）</option></select>
          <div v-for="k in ['stem_bbox','answer_bracket_bbox','options_bbox','question_bbox']" :key="k">{{ k }}: {{ p[k] }}</div>
          <button v-if="page.status==='DRAFT'" @click="mapping.splice(i,1);draw()">移除本页映射</button>
        </div>
        <label v-if="page.status==='DRAFT'"><input v-model="blankReferenceConfirmed" type="checkbox"/>确认参考卷括号内为空白；标准答案来自已审核题库，不使用写满答案的卷面作差分背景。</label>
        <button :disabled="busy||page.status!=='DRAFT'" @click="run(save)">保存本页标定</button>
        <button :disabled="busy||page.status!=='DRAFT'" @click="run(activate)">完整校验并激活整套</button>
      </div>
      <canvas ref="canvas" @pointerdown="down" @pointerup="up" />
    </div>
    <h2>答案识别与待复核</h2>
    <button v-for="t in tasks" :key="t.task_id" :disabled="busy" @click="run(()=>task(t.task_id))">{{ t.task_id }} · {{ t.status }}</button>
    <div v-if="detail">
      <button :disabled="busy" @click="run(recover)">先尝试本地安全恢复（不收费、不覆盖审核）</button>
      <p>整份状态：{{ detail.status }}。不确定识别不是错题，只有教师确认才生成成绩及错题。</p>
      <div v-for="p in detail.pages" :key="p.id" class="card page-review"><p>{{ p.status }} {{ p.reason }}（无法安全配准时请重拍或教师核对，不会使用其他版本坐标）</p><details><summary>原始页与配准证据</summary><img :src="evidence['original-'+p.id]" alt="学生原页"/><img v-if="evidence['aligned-'+p.id]" :src="evidence['aligned-'+p.id]" alt="配准页"/><pre>{{ p.evidence }}</pre></details>
        <details v-if="p.status==='UNMATCHED'"><summary>教师核对页身份与人工配准（不代表自动匹配通过）</summary><p>先查看原图和对应空白参考卷。按顺时针填写四个相同印刷定位点的原图/参考图像素坐标，不得使用手写笔迹作定位点。范围、印刷背景、版本和重复页校验不通过时仍拒绝；所有答案仍待逐题复核。</p>
          <select v-model="registration(p.id).page_id" aria-label="人工配准参考页" @change="run(()=>showReference(registration(p.id).page_id))"><option :value="0">选择核对过的参考页</option><option v-for="ref in detail.allowed_pages" :key="ref.id" :value="ref.id">第{{ ref.page_index+1 }}页 · v{{ ref.export_version }} · {{ ref.page_uid }}</option></select>
          <img v-if="evidence['registration-reference-'+registration(p.id).page_id]" :src="evidence['registration-reference-'+registration(p.id).page_id]" alt="人工配准参考卷"/>
          <label>原图四点<textarea v-model="registration(p.id).original" aria-label="原图四点" placeholder="[[x1,y1],[x2,y2],[x3,y3],[x4,y4]]"/></label>
          <label>参考卷四点<textarea v-model="registration(p.id).reference" aria-label="参考卷四点"/></label>
          <p>整页弯曲时可逐题人工核对原照片的完整题干、括号、选项四边形。逐题组合不是自动配准成功，不生成或补写笔迹，所有答案仍须教师复核。</p>
          <label>逐题原图映射（可选）<textarea v-model="registration(p.id).regions" aria-label="逐题原图映射" placeholder='[{"placement_id":1,"original_polygon":[[x1,y1],[x2,y2],[x3,y3],[x4,y4]]}]'/></label>
          <pre v-if="registration(p.id).page_id">{{ detail.allowed_pages.find((ref:any)=>ref.id===registration(p.id).page_id)?.placements.map((q:any)=>({placement_id:q.id,question_number:q.question_number})) }}</pre>
          <label>页标、题号与版本核对依据<input v-model="registration(p.id).note" aria-label="人工配准核对依据"/></label>
          <button :disabled="busy" @click="run(()=>registerPage(p))">记录教师人工配准并生成待复核候选</button>
        </details>
      </div>
      <div v-for="r in detail.reads" :key="r.id" class="card">
        <h3>第{{ r.number }}题 · {{ r.status }}</h3><p>{{ r.question_text }}</p><p>识别候选：{{ r.symbol }} · {{ r.reason }} · 标准答案：{{ r.answer }}</p>
        <p>左：学生括号裁切；右：模板剔除后的新增笔迹</p><img class="crop" :src="evidence['crop-'+r.id]" alt="学生括号"/><img class="crop" :src="evidence['ink-'+r.id]" alt="提取笔迹"/>
        <details><summary>标准空白页与定位依据</summary><img :src="evidence['template-'+r.id]" alt="标准模板"/><pre>{{ r.evidence }}</pre></details>
        <input v-model="decisions[r.id]" :disabled="busy" placeholder="A/B/C/D、AB等多选或BLANK" aria-label="人工确认答案" />
        <input v-model="notes[r.id]" :disabled="busy" placeholder="复核/更正依据（必填）" aria-label="复核依据" />
        <button :disabled="busy" @click="run(()=>confirm(r))">确认或审计改判</button>
        <div v-if="r.status!=='CONFIRMED'"><input v-model="relocation[r.id]" aria-label="重定位括号坐标"/><button :disabled="busy" @click="run(()=>relocate(r))">按题干内新坐标重识别</button></div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.known{padding:24px;max-width:1400px;margin:auto}.mapping{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:20px}.card{padding:16px;border:1px solid #cbd5e1;border-radius:8px;margin:12px 0}button,input,select{padding:8px;margin:5px;max-width:100%}canvas{width:100%;height:auto;touch-action:none;border:1px solid #94a3b8}img{max-width:45%;vertical-align:top}.crop{min-width:150px;image-rendering:auto;max-height:100px}pre{white-space:pre-wrap;overflow-wrap:anywhere}@media(max-width:900px){.mapping{grid-template-columns:1fr}}
</style>
