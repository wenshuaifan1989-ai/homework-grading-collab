const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const ts = require(path.join(root, 'node_modules/typescript'));
const source = fs.readFileSync(path.join(root, 'src/components/student/StudentPhotoSubmission.vue'), 'utf8').match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1];
const helpersModule = {exports:{}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(root, 'src/student/workbench.ts'), 'utf8'), {compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText, {module:helpersModule,exports:helpersModule.exports,Date,Intl,Set,Math});
function harness(options = {}) {
  const revoked = [];
  const requests = [];
  const events = [];
  const focused = [];
  const handheld = {value:!!options.handheld};
  const watchers=[];
  const props = {assignment:{id:123,subject:'math',grade:'grade7',student_id:456,status:'published',submitted:false},studentId:456};
  const studentExperience = {phoneTransfer:options.phone ? {createLink:async()=>{},getProgress:async()=>{}} : undefined};
  let n = 0;
  const api = {
    getAssignments: async () => ({data:{data:[]}}),
    submitAssignment: async (form, key) => {requests.push({form,key}); throw Error('synthetic offline');},
  };
  const vue = {ref:value=>({value}), computed:get=>({get value(){return get();}}), nextTick:async()=>{}, onMounted:()=>{}, onBeforeUnmount:()=>{},watch:(source,callback)=>{watchers.push({source,callback});}};
  const media = {getUserMedia:async()=>{throw Object.assign(Error('denied'),{name:'NotAllowedError'});}};
  const module = {exports:{}};
  const context = {module, exports:module.exports, console, Date, Intl, Set, Math, File, Blob, FormData, crypto,
    defineProps:()=>props, defineEmits:()=>(...args)=>events.push(args), defineExpose:()=>{},
    URL:{createObjectURL:()=>`blob:synthetic-${++n}`,revokeObjectURL:url=>revoked.push(url)},
    navigator:{mediaDevices:media}, window:{isSecureContext:options.secure !== false},
    document:{getElementById:id=>({focus:()=>{focused.push(id);}}),createElement:()=>({getContext:()=>({drawImage:()=>{}}),toBlob:callback=>callback(new Blob(['photo'],{type:'image/jpeg'}))})},
    require:name=>name==='vue'?vue:name==='@/student/device'?{useStudentHandheld:()=>handheld}:name==='@/stores/auth'?{useAuthStore:()=>({user:{role:'student'}})}:name==='@/api/student'?{studentApi:api}:name==='@/student/experience'?{studentExperience}:name==='@/student/workbench'?helpersModule.exports:{}
  };
  const exports = '\nexport {appendPhotos, removePhoto, movePhoto, onFileChange, selectedFiles, uploadPreviews, uploadError, submissionKey, submitting, submitAssignment, error, openCamera, closeCamera, takePhoto, cameraDialog, cameraVideo, cameraReady, cameraError, step, receipt, reviewPhotos, reviewDialog, photoDialog, previewPhoto, showPhoto, backToPhotos, requestClose, photoAddButton, openPhotoAdd, nativeCameraInput, openNativeCamera, queueLocked};';
  vm.runInNewContext(ts.transpileModule(source+exports,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText, context);
  return {...module.exports, revoked, requests, events, focused, props, studentExperience, api, media, handheld,
    setHandheld(value){handheld.value=value;watchers.filter(w=>w.source===handheld).forEach(w=>w.callback(value));}};
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
test('before submission, reordering and deletion keep files and previews aligned',()=>{
  const h=harness(); h.appendPhotos([image('first.png'),image('second.png')]);
  assert.equal(h.requests.length,0); h.reviewPhotos();
  const original=h.uploadPreviews.value[0]; h.movePhoto(1,-1);
  assert.equal(h.selectedFiles.value[0].name,'second.png');
  assert.equal(h.uploadPreviews.value[1],original); assert.equal(h.submissionKey.value,'');
  h.removePhoto(1); assert.equal(h.revoked[0],original); assert.equal(h.selectedFiles.value.length,1);
});
test('one multipart request, duplicate-click guard, queue lock and stable key after failure',async()=>{
  const h=harness(); h.appendPhotos([image('first.png'),image('second.png')]);
  h.reviewPhotos();
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
test('an unconfirmed request cannot be changed into a second submission group',async()=>{
  const h=harness(); h.appendPhotos([image('first.png'),image('second.png')]);
  h.reviewPhotos();
  // A lost response may mean the server created the task, so changing the group is unsafe.
  await h.submitAssignment();
  const key=h.submissionKey.value;
  assert.ok(key);
  assert.equal(h.appendPhotos([image('third.png')]),false);
  h.removePhoto(0); h.movePhoto(1,-1);
  assert.deepEqual(Array.from(h.selectedFiles.value,f=>f.name),['first.png','second.png']);
  assert.equal(h.submissionKey.value,key);
  h.api.submitAssignment=async(form,retryKey)=>{
    assert.equal(retryKey,key);
    assert.deepEqual(form.getAll('files').map(f=>f.name),['first.png','second.png']);
    return {data:{data:{task_id:'synthetic-existing-task',status:'WAIT_REVIEW',image_count:2}}};
  };
  await h.submitAssignment();
  assert.equal(h.selectedFiles.value.length,0);
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
test('captured JPEG joins queue and camera stays ready for the next page',async()=>{
  const h=harness(); const dialog=camera(h); let stopped=0;
  h.media.getUserMedia=async options=>{assert.equal(options.audio,false);return {getTracks:()=>[{stop:()=>stopped++}]};};
  await h.openCamera(); assert.equal(h.cameraReady.value,true); await h.takePhoto();
  assert.equal(h.selectedFiles.value.length,1); assert.equal(h.selectedFiles.value[0].type,'image/jpeg');
  assert.equal(dialog.open,true); assert.equal(stopped,0); assert.equal(h.cameraReady.value,true);
  h.closeCamera(); assert.equal(stopped,1); assert.equal(h.cameraVideo.value.srcObject,null);
});

test('missing server task receipt retains photos and the idempotency key',async()=>{
  const h=harness();h.appendPhotos([image('first.png')]);h.reviewPhotos();h.api.submitAssignment=async()=>({data:{data:{}}});
  await h.submitAssignment();assert.equal(h.selectedFiles.value.length,1);assert.ok(h.submissionKey.value);assert.match(h.error.value,/任务编号/);
});
test('successful receipt clears photos, stays visible and blocks another submission in the same dialog',async()=>{
  const h=harness();h.appendPhotos([image('first.png')]);h.reviewPhotos();h.api.submitAssignment=async()=>({data:{data:{task_id:'synthetic-task',status:'PENDING',image_count:1}}});
  await h.submitAssignment();assert.equal(h.selectedFiles.value.length,0);assert.equal(h.uploadPreviews.value.length,0);assert.equal(h.submissionKey.value,'');assert.equal(h.revoked.length,1);
  assert.equal(h.step.value,'receipt'); assert.equal(h.receipt.value.task_id,'synthetic-task'); assert.equal(h.error.value,'');
  assert.equal(h.appendPhotos([image('again.png')]),false); await h.submitAssignment();
  assert.equal(h.events.filter(event=>event[0]==='submitted').length,1);
  h.requestClose(); assert.equal(h.events.at(-1)[0],'cancel');
});

test('review step requires photos and an ambiguous retry retains the same review group',async()=>{
  const h=harness(); h.reviewPhotos(); assert.equal(h.step.value,'add');
  h.appendPhotos([image('first.png'),image('second.png')]); h.reviewPhotos(); assert.equal(h.step.value,'review');
  await h.submitAssignment(); assert.equal(h.step.value,'review'); assert.ok(h.submissionKey.value);
  h.requestClose(); assert.equal(h.events.at(-1)[0],'cancel'); assert.equal(h.selectedFiles.value.length,2);
});
test('first submit opens one nine-photo reminder; any thumbnail opens its original without a checklist',async()=>{
  const h=harness();
  h.appendPhotos(Array.from({length:9},(_,i)=>image('page-'+(i+1)+'.png')));
  h.reviewDialog.value={open:false,showModal(){this.open=true},close(){this.open=false}};
  h.photoDialog.value={open:false,showModal(){this.open=true},close(){this.open=false}};
  await h.reviewPhotos();
  assert.equal(h.step.value,'review'); assert.equal(h.reviewDialog.value.open,true);
  assert.equal(h.uploadPreviews.value.length,9); assert.equal(h.requests.length,0);
  h.showPhoto(7);
  assert.equal(h.photoDialog.value.open,true); assert.equal(h.previewPhoto.value.number,8);
  h.backToPhotos();
  assert.equal(h.step.value,'add'); assert.equal(h.reviewDialog.value.open,false);
  assert.equal(h.selectedFiles.value.length,9);
});

test('computer photo-add directly opens its own camera without any QR provider or method selector',async()=>{
  const h=harness({phone:true}); const dialog=camera(h);
  let cameraCalls=0, linkCalls=0;
  h.studentExperience.phoneTransfer.createLink=async()=>{linkCalls++;};
  h.media.getUserMedia=async()=>{cameraCalls++;throw Object.assign(Error('denied'),{name:'NotAllowedError'});};
  h.openPhotoAdd(); await new Promise(setImmediate);
  assert.equal(cameraCalls,1); assert.equal(dialog.open,true); assert.equal(linkCalls,0);
  assert.equal(h.requests.length,0); assert.match(h.cameraError.value,/权限/);
  assert.equal('openPhoneTransfer' in h,false);
});

test('handheld capture uses the native back camera on both HTTPS and LAN HTTP without a method or QR detour',async()=>{
  for(const secure of [true,false]) {
    const h=harness({handheld:true,phone:true,secure}); camera(h);
    let nativeCalls=0, cameraCalls=0, linkCalls=0;
    h.nativeCameraInput.value={click(){nativeCalls++;}};
    h.media.getUserMedia=async()=>{cameraCalls++;throw Error('mobile must use the native camera');};
    h.studentExperience.phoneTransfer.createLink=async()=>{linkCalls++;};
    h.openPhotoAdd();
    assert.equal(nativeCalls,1); assert.equal(h.cameraDialog.value.open,false);
    await h.openCamera();
    assert.equal(nativeCalls,2); assert.equal(cameraCalls,0);
    assert.equal(linkCalls,0); assert.equal(h.requests.length,0);
  }
});

test('native capture cancellation, consecutive photos and album selection preserve a single editable nine-photo group',()=>{
  const h=harness({handheld:true,phone:true}); let cameraCalls=0;
  h.nativeCameraInput.value={click(){cameraCalls++;}};
  function choose(files) { const input={files,value:'selected'}; h.onFileChange({target:input}); assert.equal(input.value,''); }
  choose([]); assert.equal(h.selectedFiles.value.length,0);
  h.openNativeCamera(); choose([image('camera-page-1.png')]);
  h.openNativeCamera(); choose([image('camera-page-2.png')]);
  choose(Array.from({length:7},(_,i)=>image(`album-page-${i+3}.png`)));
  assert.equal(h.selectedFiles.value.length,9); assert.equal(cameraCalls,2);
  h.openNativeCamera(); assert.equal(cameraCalls,2);
  choose([image('tenth.png')]); assert.equal(h.selectedFiles.value.length,9);
  assert.match(h.uploadError.value,/最多还能添加 0/);
  h.movePhoto(8,-1); assert.equal(h.selectedFiles.value[7].name,'album-page-9.png');
  h.removePhoto(8); assert.equal(h.selectedFiles.value.length,8);
  h.openNativeCamera(); assert.equal(cameraCalls,3);
  choose([image('replacement.png')]); assert.equal(h.selectedFiles.value.length,9);
  assert.equal(h.requests.length,0);
});

test('mobile preview is mandatory and failed nine-photo uploads retry the same assignment, order and key',async()=>{
  const h=harness({handheld:true,phone:true});
  h.appendPhotos(Array.from({length:9},(_,i)=>image(`page-${i+1}.png`)));
  await h.submitAssignment(); assert.equal(h.requests.length,0);
  h.reviewDialog.value={open:false,showModal(){this.open=true},close(){this.open=false}};
  await h.reviewPhotos(); assert.equal(h.reviewDialog.value.open,true);
  await h.submitAssignment(); const key=h.submissionKey.value;
  assert.ok(key); assert.equal(h.selectedFiles.value.length,9);
  let nativeCalls=0; h.nativeCameraInput.value={click(){nativeCalls++;}};
  h.openNativeCamera();
  assert.equal(nativeCalls,0);
  h.api.submitAssignment=async(form,retryKey)=>{
    assert.equal(retryKey,key); assert.equal(form.get('assignment_id'),'123'); assert.equal(form.get('student_id'),'456');
    assert.deepEqual(form.getAll('files').map(f=>f.name),Array.from({length:9},(_,i)=>`page-${i+1}.png`));
    return {data:{data:{task_id:'synthetic-mobile-task',status:'WAIT_REVIEW',image_count:9}}};
  };
  await h.submitAssignment(); assert.equal(h.receipt.value.status,'WAIT_REVIEW');
  assert.equal(h.receipt.value.image_count,9); assert.equal(h.selectedFiles.value.length,0);
  h.openNativeCamera(); assert.equal(nativeCalls,0);
});

test('all devices render local photo or album controls and never resurrect QR upload from a legacy provider',async()=>{
  const vue=require(path.join(root,'node_modules/vue'));
  const {parse,compileScript}=require(path.join(root,'node_modules/@vue/compiler-sfc'));
  const {renderToString}=require(path.join(root,'node_modules/@vue/server-renderer'));
  const descriptor=parse(fs.readFileSync(path.join(root,'src/components/student/StudentPhotoSubmission.vue'),'utf8')).descriptor;
  const compiled=compileScript(descriptor,{id:'local-photo-test',inlineTemplate:true});
  for(const handheld of [true,false]) for(const secure of [true,false]) {
    const module={exports:{}};
    vm.runInNewContext(ts.transpileModule(compiled.content,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText,{
      module,exports:module.exports,URL,File,Blob,FormData,crypto,window:{isSecureContext:secure},
      require:name=>name==='vue'?vue:name==='@/student/device'?{useStudentHandheld:()=>vue.ref(handheld)}
        :name==='@/student/experience'?{studentExperience:{phoneTransfer:{createLink:async()=>assert.fail('no QR request')}}}
        :name==='@/student/workbench'?helpersModule.exports:name==='@/api/student'?{studentApi:{}}:{},
    });
    const html=await renderToString(vue.createSSRApp(module.exports.default,{assignment:{id:123,title:'合成作业',subject:'math',class_name:'合成班级',status:'published',submitted:false},studentId:456}));
    assert.match(html,/aria-label="从相册选择作业照片"[^>]*multiple/);
    assert.match(html,/从相册选择/);
    assert.doesNotMatch(html,/手机扫码上传|选择拍照方式|电脑显示二维码|扫码提交|StudentPhoneTransfer/);
    if(handheld) {
      assert.match(html,/使用手机后置相机拍作业/); assert.match(html,/capture="environment"/); assert.match(html,/拍照添加/);
    } else if(secure) assert.match(html,/拍照添加/);
    else assert.match(html,/使用本机系统相机拍作业/);
  }
});

test('changing to handheld actions stops the former computer camera while preserving the local photo queue',async()=>{
  const h=harness({phone:true}); camera(h);
  assert.equal(h.appendPhotos([image('local-page.png')]),true);
  let stopped=0; h.media.getUserMedia=async()=>({getTracks:()=>[{stop(){stopped++;}}]});
  await h.openCamera(); assert.equal(h.cameraDialog.value.open,true);
  h.setHandheld(true); assert.equal(h.cameraDialog.value.open,false); assert.equal(stopped,1);
  assert.equal(h.selectedFiles.value[0].name,'local-page.png');
  assert.equal(h.queueLocked.value,false);
});
