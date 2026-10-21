const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const ts = require(path.join(root, 'node_modules/typescript'));
const source = fs.readFileSync(path.join(root, 'src/components/student/StudentPhotoSubmission.vue'), 'utf8').match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1];
function harness() {
  const revoked = [];
  const requests = [];
  let n = 0;
  const api = {
    getAssignments: async () => ({data:{data:[]}}),
    submitAssignment: async (form, key) => {requests.push({form,key}); throw Error('synthetic offline');},
  };
  const vue = {ref:value=>({value}), computed:get=>({get value(){return get();}}), nextTick:async()=>{}, onMounted:()=>{}, onBeforeUnmount:()=>{}};
  const media = {getUserMedia:async()=>{throw Object.assign(Error('denied'),{name:'NotAllowedError'});}};
  const module = {exports:{}};
  const context = {module, exports:module.exports, console, Date, Intl, Set, Math, File, Blob, FormData, crypto,
    defineProps:()=>({assignment:{id:123,subject:'math',grade:'grade7',student_id:456},studentId:456}), defineEmits:()=>()=>{}, defineExpose:()=>{},
    URL:{createObjectURL:()=>`blob:synthetic-${++n}`,revokeObjectURL:url=>revoked.push(url)},
    navigator:{mediaDevices:media},
    document:{createElement:()=>({getContext:()=>({drawImage:()=>{}}),toBlob:callback=>callback(new Blob(['photo'],{type:'image/jpeg'}))})},
    require:name=>name==='vue'?vue:name==='@/stores/auth'?{useAuthStore:()=>({user:{role:'student'}})}:name==='@/api/student'?{studentApi:api}:{}
  };
  const exports = '\nexport {appendPhotos, removePhoto, movePhoto, onFileChange, selectedFiles, uploadPreviews, uploadError, submissionKey, submitting, submitAssignment, error, openCamera, closeCamera, takePhoto, cameraDialog, cameraVideo, cameraReady, cameraError};';
  vm.runInNewContext(ts.transpileModule(source+exports,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText, context);
  return {...module.exports, revoked, requests, api, media};
}
const image = name=>new File(['synthetic'],name,{type:'image/png'});
test('append preserves existing photos; cancellation/invalid/over-limit leave the queue intact',()=>{
  const h=harness();
  h.appendPhotos([image('first.png')]); h.appendPhotos([image('second.png')]);
  assert.equal(h.selectedFiles.value.length,2);
  h.appendPhotos([]);
  assert.equal(h.appendPhotos([new File(['invalid'],'invalid.txt',{type:'text/plain'})]),false);
  assert.equal(h.appendPhotos([new File([new Uint8Array(10*1024*1024+1)],'large.png',{type:'image/png'})]),false);
  assert.equal(h.appendPhotos(Array.from({length:8},(_,i)=>image(i+'.png'))),false);
  assert.equal(h.selectedFiles.value.length,2);
  assert.equal(h.appendPhotos(Array.from({length:7},(_,i)=>image(i+'.png'))),true);
  assert.equal(h.selectedFiles.value.length,9);
  assert.equal(h.appendPhotos([image('tenth.png')]),false);
});
test('reordering and deletion keep previews aligned and invalidate the submission key',()=>{
  const h=harness(); h.appendPhotos([image('first.png'),image('second.png')]);
  const original=h.uploadPreviews.value[0]; h.submissionKey.value='previous'; h.movePhoto(1,-1);
  assert.equal(h.selectedFiles.value[0].name,'second.png');
  assert.equal(h.uploadPreviews.value[1],original); assert.equal(h.submissionKey.value,'');
  h.removePhoto(1); assert.equal(h.revoked[0],original); assert.equal(h.selectedFiles.value.length,1);
});
test('one multipart request, duplicate-click guard, queue lock and stable key after failure',async()=>{
  const h=harness(); h.appendPhotos([image('first.png'),image('second.png')]);
  let rejectRequest;
  h.api.submitAssignment=(form,key)=>{h.requests.push({form,key});return new Promise((_,reject)=>{rejectRequest=reject;});};
  const assignment={id:123,subject:'math',grade:'grade7',student_id:456};
  const pending=h.submitAssignment(assignment);
  await h.submitAssignment(assignment);
  assert.equal(h.requests.length,1);
  assert.equal(h.appendPhotos([image('third.png')]),false); h.removePhoto(0); h.movePhoto(1,-1);
  assert.equal(h.selectedFiles.value.length,2);
  assert.deepEqual(h.requests[0].form.getAll('files').map(f=>f.name),['first.png','second.png']);
  assert.equal(h.requests[0].form.get('assignment_id'),'123'); assert.equal(h.requests[0].form.get('student_id'),'456');
  const key=h.requests[0].key; rejectRequest(Error('synthetic offline')); await pending;
  assert.equal(h.selectedFiles.value.length,2); assert.equal(h.submissionKey.value,key); assert.equal(h.submitting.value,false);
  h.api.submitAssignment=async(form,key)=>{h.requests.push({form,key});throw Error('synthetic offline');};
  await h.submitAssignment(assignment); assert.equal(h.requests[1].key,key);
});
function camera(h){
  const dialog={open:false,showModal(){this.open=true;},close(){this.open=false;}};
  h.cameraDialog.value=dialog; h.cameraVideo.value={srcObject:null,videoWidth:640,videoHeight:480,play:async()=>{}};
  return dialog;
}
test('camera denial shows recovery; late stream after closing is stopped',async()=>{
  const h=harness(); camera(h); await h.openCamera(); assert.match(h.cameraError.value,/权限/); assert.equal(h.cameraReady.value,false);
  h.closeCamera(); let deliver; let stopped=0; h.media.getUserMedia=()=>new Promise(resolve=>{deliver=resolve;});
  const pending=h.openCamera(); h.closeCamera(); deliver({getTracks:()=>[{stop:()=>stopped++}]}); await pending;
  assert.equal(stopped,1); assert.equal(h.cameraReady.value,false); assert.equal(h.cameraVideo.value.srcObject,null);
});
test('captured JPEG joins queue; camera closes and stops tracks',async()=>{
  const h=harness(); const dialog=camera(h); let stopped=0;
  h.media.getUserMedia=async options=>{assert.equal(options.audio,false);return {getTracks:()=>[{stop:()=>stopped++}]};};
  await h.openCamera(); assert.equal(h.cameraReady.value,true); await h.takePhoto();
  assert.equal(h.selectedFiles.value.length,1); assert.equal(h.selectedFiles.value[0].type,'image/jpeg');
  assert.equal(dialog.open,false); assert.equal(stopped,1); assert.equal(h.cameraVideo.value.srcObject,null);
});

test('missing server task receipt retains photos and the idempotency key',async()=>{
  const h=harness();h.appendPhotos([image('first.png')]);h.api.submitAssignment=async()=>({data:{data:{}}});
  await h.submitAssignment();assert.equal(h.selectedFiles.value.length,1);assert.ok(h.submissionKey.value);assert.match(h.error.value,/任务编号/);
});
test('successful receipt clears file previews and allows a new queue',async()=>{
  const h=harness();h.appendPhotos([image('first.png')]);h.api.submitAssignment=async()=>({data:{data:{task_id:'synthetic-task',status:'PENDING',image_count:1}}});
  await h.submitAssignment();assert.equal(h.selectedFiles.value.length,0);assert.equal(h.uploadPreviews.value.length,0);assert.equal(h.submissionKey.value,'');assert.equal(h.revoked.length,1);
});
