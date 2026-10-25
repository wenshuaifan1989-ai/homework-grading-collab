const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const root = path.resolve(__dirname, '..')
function compile(source, deps = {}, globals = {}) {
  const module = { exports: {} }
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText,
    { module, exports: module.exports, Set, Map, Math, Date, crypto, atob, Blob,
      URL: { revokeObjectURL: () => {} }, window: { addEventListener() {}, removeEventListener() {} },
      require: name => deps[name] || {}, ...globals })
  return module.exports
}
const experienceSource = fs.readFileSync(path.join(root, 'src/student/experience.ts'), 'utf8')
const workbench = compile(fs.readFileSync(path.join(root, 'src/student/workbench.ts'), 'utf8'))
const source = fs.readFileSync(path.join(root, 'src/views/StudentMistakesView.vue'), 'utf8').match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1]
function deferred() { let resolve, reject; const promise = new Promise((a,b) => { resolve=a; reject=b }); return {promise,resolve,reject} }
function setup(options = {}) {
  const items = [
    { id: 1, student_id: 92001, assignment_id: 11, assignment_title: '合成数学作业甲', subject: 'math', question_no: '1', status: 'open' },
    { id: 2, student_id: 92001, assignment_id: 12, assignment_title: '合成英语作业', subject: 'english', question_no: '2', status: 'pending' },
    { id: 3, student_id: 92001, assignment_id: 11, assignment_title: '合成数学作业甲', subject: 'math', question_no: '3', status: 'correction_submitted' },
    { id: 4, student_id: 92001, assignment_id: 13, assignment_title: '合成数学作业乙', subject: 'math', question_no: '4', status: 'mastered' },
  ].map(item => ({ ...item, knowledge_points: [], crop_url: `/api/v1/paper/mistakes/${item.id}/image?kind=crop`,
    original_url: `/api/v1/paper/mistakes/${item.id}/image?kind=original`,
    question: { question_text: `原始题面${item.id}`, options: ['原始选项'], correct_answer: `RAW_PRIVATE_ANSWER_${item.id}`, analysis:'RAW_PRIVATE_ANALYSIS' },
    grading_result: { student_answer: `RAW_UNCONFIRMED_STUDENT_ANSWER_${item.id}` },
  }))
  const removed = new Set(), actionCalls = [], imageCalls = [], materialCalls = [], forbiddenCalls = [], focused = [], created = [], revoked = []
  const dialog = { open:false, opens:0, showModal() { this.open=true; this.opens++ }, close() { this.open=false } }
  const paperApi = {
    studentMistakes: async id => { assert.equal(id,92001); return {items:items.filter(item=>!removed.has(item.id))} },
    image: async (url,kind) => { imageCalls.push({url,kind}); return new Blob(['synthetic-image'],{type:'image/png'}) },
    submitCorrection: async () => { forbiddenCalls.push('submitCorrection'); throw Error('student correction is not part of this page') },
    correctionHistory: async () => { forbiddenCalls.push('correctionHistory'); throw Error('student correction history is not part of this page') },
  }
  const studentApi = { getMyStudents:async()=>({data:{data:[{student_id:92001,status:'active',relationship_type:'father',classes:[{class_id:93001,class_name:'合成班级',status:'active'}]}]}}) }
  const experience = compile(experienceSource)
  experience.studentExperience.deletedMistakes=async id=>{assert.equal(id,92001);return items.filter(item=>removed.has(item.id))}
  experience.studentExperience.changeMistake=async(studentId,id,deleted,key)=>{
    actionCalls.push({studentId,id,deleted,key}); if(deleted)removed.add(id);else removed.delete(id)
    return {student_id:studentId,id,deleted}
  }
  const makeMaterial = id => ({student_id:92001,mistake_id:id,
    question:{text:`已确认题面${id}`,options:{A:'合成选项甲',B:'合成选项乙'},complete:true,image_data_url:null},
    standard_answer:{released:true,text:`已公开标准答案${id}`},student_answer:`已确认本人作答${id}`})
  if(options.materials!==false) experience.studentExperience.mistakeMaterial=async(studentId,id)=>{materialCalls.push({studentId,id});return makeMaterial(id)}
  const vue={ref:value=>({value}),computed:get=>({get value(){return get()}}),nextTick:async()=>{},onMounted:()=>{},onBeforeUnmount:()=>{}}
  const exposed='\nexport { loadStudents, loadMistakes, refreshMistakes, studentId, students, subject, subjects, groups, visibleItems, shownCount, recycleBin, canDelete, mistakes, deleted, error, notice, confirmDeleteId, pendingAction, askDelete, changeMistake, canLeave, beforeUnload, selectedIds, selectionCount, allSelected, partiallySelected, toggleAll, toggleItem, setSubject, toggleRecycleBin, materials, materialErrors, loadingMaterials, materialFor, publicAnswer, questionText, questionOptions, showDetail, clearDetail, closeDetail, showOwnImage, detailDialog, detailItem, detailKind, detailAnswer, detailOwnText, detailImage, detailBusy, detailError, printOpen, printSelection, openPrint, closePrint };'
  const view=compile(source+exposed,{
    vue,'vue-router':{onBeforeRouteLeave:()=>{}},'@/api/paper':{paperApi},'@/api/student':{studentApi},
    '@/student/experience':experience,'@/student/workbench':workbench,
    '@/student/mistakePrint':compile(fs.readFileSync(path.join(root,'src/student/mistakePrint.ts'),'utf8')),
  },{document:{getElementById:id=>({focus:()=>focused.push(id)})},URL:{createObjectURL:()=>{const url=`blob:synthetic-${created.length+1}`;created.push(url);return url},revokeObjectURL:url=>revoked.push(url)}})
  view.detailDialog.value=dialog
  return {...view,experience,paperApi,studentApi,items,removed,actionCalls,imageCalls,materialCalls,forbiddenCalls,focused,created,revoked,dialog,makeMaterial}
}
function ids(items) { return Array.from(items,item=>item.id) }

test('one active child sees one subject grouped by original assignment regardless of former correction state',async()=>{
  const h=setup();await h.loadStudents()
  assert.equal(h.studentId.value,92001);assert.equal(h.subject.value,'math')
  assert.deepEqual(Array.from(h.groups.value,group=>group.title),['合成数学作业甲','合成数学作业乙'])
  assert.deepEqual(ids(h.visibleItems.value),[1,3,4])
  h.setSubject('english');assert.deepEqual(ids(h.visibleItems.value),[2])
  h.setSubject('');assert.equal(h.groups.value.length,0)
  assert.deepEqual(h.forbiddenCalls,[]);assert.equal(h.imageCalls.length,0)
})
test('ambiguous multi-child binding is blocked and foreign-student records are filtered',async()=>{
  const h=setup();h.items.push({...h.items[0],id:5,student_id:92002})
  await h.loadStudents();assert.deepEqual(ids(h.mistakes.value),[1,2,3,4]);assert.equal(h.materialCalls.some(call=>call.id===5),false)
  h.studentApi.getMyStudents=async()=>({data:{data:[{student_id:92001,status:'active'},{student_id:92002,status:'active'}]}})
  await h.loadStudents();assert.equal(h.studentId.value,null);assert.match(h.error.value,/多个学生/);assert.equal(h.mistakes.value.length,0)
})
test('selection supports individual, all and cancel within the current subject only',async()=>{
  const h=setup();await h.loadStudents()
  h.toggleItem(h.items[0]);assert.equal(h.selectionCount.value,1);assert.equal(h.partiallySelected.value,true)
  h.toggleItem(h.items[1]);assert.equal(h.selectionCount.value,1)
  h.toggleAll();assert.deepEqual(Array.from(h.selectedIds.value),[1,3,4]);assert.equal(h.allSelected.value,true)
  h.toggleItem(h.items[2]);assert.equal(h.allSelected.value,false);assert.equal(h.selectionCount.value,2)
  h.toggleAll();h.toggleAll();assert.equal(h.selectionCount.value,0);assert.equal(h.partiallySelected.value,false)
})
test('subject changes clear selections and print snapshots while selecting the same subject preserves them',async()=>{
  const h=setup();await h.loadStudents();h.toggleAll();h.openPrint()
  assert.equal(h.printOpen.value,true);assert.deepEqual(ids(h.printSelection.value.map(row=>row.item)),[1,3,4])
  h.setSubject('math');assert.equal(h.selectionCount.value,3)
  h.setSubject('english');assert.equal(h.selectionCount.value,0);assert.equal(h.selectedIds.value.size,0)
  assert.equal(h.printOpen.value,false);assert.equal(h.printSelection.value.length,0)
  h.toggleAll();h.openPrint();assert.deepEqual(ids(h.printSelection.value.map(row=>row.item)),[2])
})
test('recycle-bin switches and refresh clear selection and cannot export removed items',async()=>{
  const h=setup();h.removed.add(3);await h.loadStudents();h.toggleAll();h.openPrint()
  h.toggleRecycleBin();assert.equal(h.recycleBin.value,true);assert.equal(h.selectedIds.value.size,0);assert.equal(h.printOpen.value,false)
  h.toggleAll();h.toggleItem(h.items[2]);h.openPrint();assert.equal(h.selectionCount.value,0);assert.equal(h.printOpen.value,false)
  h.toggleRecycleBin();h.toggleAll();h.openPrint();await h.refreshMistakes()
  assert.equal(h.selectedIds.value.size,0);assert.equal(h.printOpen.value,false);assert.equal(h.printSelection.value.length,0)
})
test('raw standard answers and raw recognized student answers are never treated as approved material',async()=>{
  const h=setup({materials:false});await h.loadStudents();const item=h.items[0]
  assert.equal(h.publicAnswer(item),'');assert.equal(h.materialFor(item),null)
  await h.showDetail(item,'standard');assert.equal(h.dialog.opens,0);assert.equal(h.imageCalls.length,0)
  await h.showDetail(item,'own');assert.equal(h.detailOwnText.value,'');assert.equal(h.imageCalls.length,1)
  assert.equal(h.questionText(item),'原始题面1');assert.equal(h.created.length,1)
})
test('only released material with matching Student.id and mistake id exposes a standard answer',async()=>{
  const h=setup();await h.loadStudents();const item=h.items[0]
  assert.equal(h.publicAnswer(item),'已公开标准答案1');assert.equal(h.questionText(item),'已确认题面1')
  assert.deepEqual(Array.from(h.questionOptions(item)),['A. 合成选项甲','B. 合成选项乙'])
  for(const material of [
    {...h.makeMaterial(1),student_id:92002}, {...h.makeMaterial(1),mistake_id:99},
    {...h.makeMaterial(1),standard_answer:{released:false,text:'NOT_RELEASED'}},
    {...h.makeMaterial(1),standard_answer:{released:'true',text:'NOT_BOOLEAN_RELEASE'}},
  ]) {h.materials.value={1:material};assert.equal(h.publicAnswer(item),'')}
})
test('mismatched provider receipts do not become viewable answer material',async()=>{
  const h=setup();h.experience.studentExperience.mistakeMaterial=async(_,id)=>({...h.makeMaterial(id),student_id:92002})
  await h.loadStudents();assert.equal(Object.keys(h.materials.value).length,0)
  assert.match(h.materialErrors.value[1],/不一致/);assert.equal(h.publicAnswer(h.items[0]),'')
})
test('approved own answer text opens on demand without fetching an image or correction history',async()=>{
  const h=setup();await h.loadStudents();assert.equal(h.detailItem.value,null);assert.equal(h.imageCalls.length,0)
  await h.showDetail(h.items[0],'own');assert.equal(h.dialog.open,true);assert.equal(h.detailOwnText.value,'已确认本人作答1')
  assert.equal(h.imageCalls.length,0);assert.deepEqual(h.forbiddenCalls,[])
  await h.closeDetail();assert.equal(h.dialog.open,false);assert.equal(h.detailItem.value,null)
  assert.deepEqual(h.focused,['mistake-1-own'])
})
test('standard answer details use the released answer only and do not fetch work images',async()=>{
  const h=setup();await h.loadStudents();await h.showDetail(h.items[0],'standard')
  assert.equal(h.dialog.open,true);assert.equal(h.detailKind.value,'standard');assert.equal(h.detailAnswer.value,'已公开标准答案1')
  assert.equal(h.imageCalls.length,0);await h.closeDetail();assert.deepEqual(h.focused,['mistake-1-standard'])
})
test('own answer falls back to the authorized crop and can load the original page',async()=>{
  const h=setup({materials:false});await h.loadStudents();await h.showDetail(h.items[0],'own')
  assert.deepEqual(h.imageCalls,[{url:h.items[0].crop_url,kind:'crop'}]);assert.equal(h.detailImage.value,'blob:synthetic-1')
  await h.showOwnImage('original');assert.equal(h.imageCalls[1].url,h.items[0].original_url);assert.equal(h.imageCalls[1].kind,'original')
  assert.deepEqual(h.revoked,['blob:synthetic-1']);await h.closeDetail();assert.deepEqual(h.revoked,['blob:synthetic-1','blob:synthetic-2'])
})
test('closing or switching subject before the detail opens does not reopen a stale dialog',async()=>{
  for(const leave of [h=>h.clearDetail(),h=>h.setSubject('english')]) {
    const h=setup();await h.loadStudents();const pending=h.showDetail(h.items[0],'own');leave(h);await pending
    assert.equal(h.dialog.opens,0);assert.equal(h.dialog.open,false);assert.equal(h.imageCalls.length,0)
  }
})
test('late own images after closing or changing Student.id never allocate a display URL',async()=>{
  for(const leave of [h=>h.clearDetail(),h=>{h.studentId.value=92002}]) {
    const h=setup({materials:false});await h.loadStudents();const result=deferred(),started=deferred();let calls=0
    h.paperApi.image=()=>{calls++;started.resolve();return result.promise}
    const pending=h.showDetail(h.items[0],'own');await started.promise;assert.equal(calls,1)
    leave(h);result.resolve(new Blob(['synthetic-image'],{type:'image/png'}));await pending
    assert.equal(h.created.length,0);assert.equal(h.detailImage.value,'')
  }
})
test('unsupported own-image content is rejected instead of becoming a displayed object URL',async()=>{
  const h=setup({materials:false});await h.loadStudents();h.paperApi.image=async()=>new Blob(['<svg></svg>'],{type:'image/svg+xml'})
  await h.showDetail(h.items[0],'own');assert.equal(h.created.length,0);assert.match(h.detailError.value,/格式暂不支持/)
})
test('a late material response for a previous student cannot publish answers in the new context',async()=>{
  const h=setup();h.studentId.value=92001;const response=deferred()
  h.experience.studentExperience.mistakeMaterial=(_,id)=>id===1?response.promise:Promise.resolve(h.makeMaterial(id))
  const pending=h.loadMistakes();await Promise.resolve();await Promise.resolve();h.studentId.value=92002
  response.resolve(h.makeMaterial(1));await pending;assert.equal(Object.keys(h.materials.value).length,0)
  assert.equal(h.publicAnswer(h.items[0]),'')
})
test('delete and restore keep the same question, original correction status and history metadata',async()=>{
  const h=setup();await h.loadStudents();const item=h.items[2];const original={...item}
  h.askDelete(item);await h.changeMistake(item,true)
  assert.deepEqual(ids(h.visibleItems.value),[1,4]);assert.deepEqual(ids(h.deleted.value),[3]);assert.equal(item.status,'correction_submitted')
  h.toggleRecycleBin();await h.changeMistake(item,false);assert.equal(h.removed.size,0)
  assert.deepEqual(item,original);assert.equal(h.actionCalls.length,2);assert.equal(h.actionCalls[0].studentId,92001)
  assert.deepEqual(h.forbiddenCalls,[]);assert.equal(h.pendingAction.value,null)
})
test('unconfirmed deletion retains its key and blocks navigation until the matching operation succeeds',async()=>{
  const h=setup();await h.loadStudents();const item=h.items[0],keys=[]
  h.experience.studentExperience.changeMistake=async(_,__,___,key)=>{keys.push(key);throw Error('synthetic offline')}
  h.askDelete(item);await h.changeMistake(item,true)
  assert.equal(h.mistakes.value.length,4);assert.equal(h.deleted.value.length,0);assert.match(h.error.value,/尚未确认/)
  assert.equal(h.canLeave(),false);h.setSubject('english');assert.equal(h.subject.value,'math')
  const event={prevented:false,preventDefault(){this.prevented=true},returnValue:undefined};h.beforeUnload(event);assert.equal(event.prevented,true)
  await h.changeMistake(h.items[2],true);assert.equal(keys.length,1)
  await h.changeMistake(item,true);assert.equal(keys[0],keys[1])
  h.experience.studentExperience.changeMistake=async(studentId,id,deleted,key)=>{assert.equal(key,keys[0]);h.removed.add(id);return {student_id:studentId,id,deleted}}
  await h.changeMistake(item,true);assert.equal(h.pendingAction.value,null);assert.equal(h.canLeave(),true)
})
test('a mismatched deletion receipt preserves the record and unresolved operation',async()=>{
  const h=setup();await h.loadStudents();const item=h.items[0]
  h.experience.studentExperience.changeMistake=async()=>({student_id:92002,id:item.id,deleted:true})
  h.askDelete(item);await h.changeMistake(item,true)
  assert.equal(h.mistakes.value.length,4);assert.equal(h.deleted.value.length,0);assert.ok(h.pendingAction.value)
  assert.equal(h.notice.value,'');assert.match(h.error.value,/不一致/)
})
test('without approved recoverable-delete services no local-only deletion is claimed as shared',async()=>{
  const h=setup();await h.loadStudents();h.experience.studentExperience.changeMistake=undefined
  assert.equal(h.canDelete.value,false);h.askDelete(h.items[0]);await h.changeMistake(h.items[0],true)
  assert.equal(h.confirmDeleteId.value,null);assert.equal(h.actionCalls.length,0);assert.equal(h.mistakes.value.length,4)
})
