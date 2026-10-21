<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref } from 'vue';
import { studentApi, type StudentAssignment } from '@/api/student';
const props = defineProps<{
    assignment: StudentAssignment;
    studentId: number;
}>();
const emit = defineEmits<{
    submitted: [
        response: {
            task_id: string;
            status: string;
            image_count: number;
        }
    ];
    cancel: [
    ];
}>();
const selectedFiles = ref<File[]>([]);
const uploadPreviews = ref<string[]>([]);
const uploadError = ref('');
const cameraDialog = ref<HTMLDialogElement | null>(null);
const cameraVideo = ref<HTMLVideoElement | null>(null);
const cameraReady = ref(false);
const cameraBusy = ref(false);
const cameraError = ref('');
const photoDialog = ref<HTMLDialogElement | null>(null);
const previewPhoto = ref<{
    url: string;
    number: number;
} | null>(null);
let cameraStream: MediaStream | null = null;
let cameraSession = 0;
const submissionKey = ref('');
const submitting = ref(false);
const error = ref('');
function clearUploadQueue() {
    uploadPreviews.value.forEach((url) => URL.revokeObjectURL(url));
    uploadPreviews.value = [];
    selectedFiles.value = [];
    submissionKey.value = '';
    uploadError.value = '';
}
function appendPhotos(files: File[]): boolean {
    if (submitting.value || !files.length)
        return false;
    if (selectedFiles.value.length + files.length > 9) {
        uploadError.value = `已有 ${selectedFiles.value.length} 张，最多还能添加 ${9 - selectedFiles.value.length} 张。`;
        return false;
    }
    const supportedTypes = new Set(['image/jpeg', 'image/png', 'image/gif', 'image/bmp']);
    const invalid = files.find((file) => !supportedTypes.has(file.type) || file.size > 10 * 1024 * 1024 || !file.size);
    if (invalid) {
        uploadError.value = !invalid.size ? '图片为空，请重新拍照或选择图片。'
            : invalid.size > 10 * 1024 * 1024 ? '单张图片不能超过 10MB，请压缩后重选。'
                : '请选择 JPG、PNG、GIF 或 BMP 图片。';
        return false;
    }
    uploadPreviews.value.push(...files.map((file) => URL.createObjectURL(file)));
    selectedFiles.value.push(...files);
    submissionKey.value = '';
    uploadError.value = '';
    return true;
}
function onFileChange(event: Event) {
    const input = event.target as HTMLInputElement;
    const added = appendPhotos(Array.from(input.files || []));
    input.value = '';
    if (added && cameraDialog.value?.open)
        closeCamera();
}
function removePhoto(index: number) {
    if (submitting.value || index < 0 || index >= selectedFiles.value.length)
        return;
    URL.revokeObjectURL(uploadPreviews.value[index]);
    selectedFiles.value.splice(index, 1);
    uploadPreviews.value.splice(index, 1);
    submissionKey.value = '';
    uploadError.value = '';
}
function movePhoto(index: number, direction: number) {
    const target = index + direction;
    if (submitting.value || index < 0 || index >= selectedFiles.value.length || target < 0 || target >= selectedFiles.value.length)
        return;
    [selectedFiles.value[index], selectedFiles.value[target]] = [selectedFiles.value[target], selectedFiles.value[index]];
    [uploadPreviews.value[index], uploadPreviews.value[target]] = [uploadPreviews.value[target], uploadPreviews.value[index]];
    submissionKey.value = '';
}
function showPhoto(index: number) {
    previewPhoto.value = { url: uploadPreviews.value[index], number: index + 1 };
    photoDialog.value?.showModal();
}
function stopCamera() {
    cameraSession += 1;
    cameraStream?.getTracks().forEach((track) => track.stop());
    cameraStream = null;
    cameraReady.value = false;
    if (cameraVideo.value)
        cameraVideo.value.srcObject = null;
}
function closeCamera() {
    cameraDialog.value?.close();
    stopCamera();
}
async function openCamera() {
    if (submitting.value || selectedFiles.value.length >= 9)
        return;
    stopCamera();
    const session = cameraSession;
    cameraError.value = '';
    cameraReady.value = false;
    cameraDialog.value?.showModal();
    if (!navigator.mediaDevices?.getUserMedia) {
        cameraError.value = '当前浏览器无法直接使用摄像头，可使用下方系统相机或从相册选择。';
        return;
    }
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1440 } } });
        if (!cameraDialog.value?.open || session !== cameraSession) {
            stream.getTracks().forEach((track) => track.stop());
            return;
        }
        cameraStream = stream;
        await nextTick();
        if (!cameraVideo.value) {
            stopCamera();
            return;
        }
        cameraVideo.value.srcObject = stream;
        await cameraVideo.value.play();
        if (session !== cameraSession)
            return;
        cameraReady.value = true;
    }
    catch (err: any) {
        if (session !== cameraSession)
            return;
        stopCamera();
        cameraError.value = err?.name === 'NotAllowedError'
            ? '未获得摄像头权限。可在浏览器中允许使用摄像头，或从相册选择。'
            : '摄像头暂时无法使用，请检查设备，或使用下方系统相机、相册入口。';
    }
}
async function takePhoto() {
    if (!cameraReady.value || cameraBusy.value || submitting.value)
        return;
    const video = cameraVideo.value;
    if (!video?.videoWidth || !video.videoHeight)
        return;
    const session = cameraSession;
    cameraBusy.value = true;
    try {
        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const context = canvas.getContext('2d');
        if (!context)
            throw new Error('无法生成照片，请使用系统相机或相册。');
        context.drawImage(video, 0, 0);
        const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.9));
        if (!blob)
            throw new Error('拍照未成功，请重试。');
        if (!cameraDialog.value?.open || session !== cameraSession)
            return;
        if (appendPhotos([new File([blob], `作业照片-${Date.now()}.jpg`, { type: 'image/jpeg' })]))
            closeCamera();
        else
            cameraError.value = uploadError.value;
    }
    catch (err: any) {
        cameraError.value = err.message || '拍照失败，请重试。';
    }
    finally {
        cameraBusy.value = false;
    }
}
async function submitAssignment() {
    const assignment = props.assignment;
    if (submitting.value)
        return;
    error.value = '';
    if (!selectedFiles.value.length || selectedFiles.value.length > 9) {
        error.value = '请一次选择 1 至 9 张整份作业图片。';
        return;
    }
    submitting.value = true;
    try {
        if (!submissionKey.value) {
            const nonce = typeof crypto !== 'undefined' && crypto.randomUUID
                ? crypto.randomUUID()
                : `${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}`;
            submissionKey.value = `web_${nonce}`;
        }
        const form = new FormData();
        selectedFiles.value.forEach((file) => form.append('files', file, file.name));
        form.append('subject', assignment.subject);
        form.append('grade', assignment.grade);
        form.append('mode', 'vision');
        form.append('assignment_id', String(assignment.id));
        if (assignment.student_id || props.studentId) {
            form.append('student_id', String(assignment.student_id || props.studentId));
        }
        const { data } = await studentApi.submitAssignment(form, submissionKey.value);
        if (!data.data?.task_id)
            throw new Error('服务未返回任务编号，请保留照片并重试。');
        emit('submitted', data.data);
        clearUploadQueue();
    }
    catch (requestError: any) {
        error.value = requestError.response?.data?.detail || requestError.response?.data?.message || requestError.message || '提交失败，请保留照片后重试。';
    }
    finally {
        submitting.value = false;
    }
}
defineExpose({ hasDraft: computed(() => selectedFiles.value.length > 0), busy: computed(() => submitting.value) });
onBeforeUnmount(() => { stopCamera(); clearUploadQueue(); });
</script>
<template>
  <section class="submission" aria-labelledby="submission-heading">
    <header class="submission-header">
<div>
<p>一次提交整份作业</p>
<h2 id="submission-heading">{{ assignment.title }}</h2>
</div>
<button type="button" class="btn btn-secondary btn-sm" :disabled="submitting" @click="$emit('cancel')">收起</button>
</header>
    <p v-if="error" class="photo-error" role="alert">{{ error }}</p>
    <div class="student-upload-box">

            <div class="photo-queue-heading">
<strong>准备作业照片</strong>
<span aria-live="polite">{{ selectedFiles.length }} / 9 张</span>
</div>
            <p class="muted">拍清整页，按页码添加；拍照后先检查，最后一次提交。</p>
            <div class="photo-add-actions">
              <button type="button" class="btn btn-primary" :disabled="submitting || selectedFiles.length >= 9" @click="openCamera">拍照添加</button>
              <label class="student-file-picker" :class="{ 'is-disabled': submitting || selectedFiles.length >= 9 }">从相册选择<input aria-label="从相册选择作业照片" type="file" accept="image/jpeg,image/png,image/gif,image/bmp" multiple :disabled="submitting || selectedFiles.length >= 9" @change="onFileChange" />
</label>
            </div>
            <p v-if="uploadError" class="photo-error" role="alert">{{ uploadError }}</p>
            <ol v-if="selectedFiles.length" class="photo-queue" aria-label="待提交作业照片">
              <li v-for="(file, index) in selectedFiles" :key="uploadPreviews[index]" class="photo-item">
                <button type="button" class="photo-thumbnail" :aria-label="`预览第 ${index + 1} 张照片`" @click="showPhoto(index)">
<img :src="uploadPreviews[index]" :alt="`第 ${index + 1} 张作业照片`" />
<span>第 {{ index + 1 }} 页 · 点击放大</span>
</button>
                <span class="photo-name" :title="file.name">{{ file.name }}</span>
                <div class="photo-controls">
                  <button type="button" :aria-label="`前移第 ${index + 1} 张照片`" :disabled="submitting || index === 0" @click="movePhoto(index, -1)">前移</button>
                  <button type="button" :aria-label="`后移第 ${index + 1} 张照片`" :disabled="submitting || index === selectedFiles.length - 1" @click="movePhoto(index, 1)">后移</button>
                  <button type="button" :aria-label="`删除第 ${index + 1} 张照片`" :disabled="submitting" @click="removePhoto(index)">删除</button>
                </div>
              </li>
            </ol>
            <p v-else class="muted">还没有添加照片。支持 JPG、PNG、GIF、BMP，每张不超过 10MB。</p>
            <button class="btn btn-primary" :disabled="submitting || !selectedFiles.length" @click="submitAssignment">{{ submitting ? '提交中…' : `提交 ${selectedFiles.length} 张图片` }}</button>
    </div>
    <dialog ref="cameraDialog" class="photo-dialog" aria-labelledby="camera-heading" @close="stopCamera" @cancel="stopCamera">
      <div class="photo-dialog-heading">
<h2 id="camera-heading">拍摄作业</h2>
<button type="button" class="btn btn-secondary btn-sm" @click="closeCamera">关闭相机</button>
</div>
      <p class="muted">将整页放入画面，保持光线充足，文字清晰后再拍摄。</p>
      <video ref="cameraVideo" autoplay muted playsinline class="camera-video" aria-label="作业拍摄画面">
</video>
      <p v-if="cameraError" class="photo-error" role="alert">{{ cameraError }}</p>
      <p v-else-if="!cameraReady" role="status">正在打开相机，请按浏览器提示允许使用摄像头…</p>
      <div class="photo-add-actions">
        <button type="button" class="btn btn-primary" :disabled="!cameraReady || cameraBusy" @click="takePhoto">{{ cameraBusy ? '正在保存…' : '拍照并添加' }}</button>
        <label class="student-file-picker">系统相机 / 选择照片<input aria-label="系统相机或选择照片" type="file" accept="image/jpeg,image/png,image/gif,image/bmp" capture="environment" :disabled="cameraBusy" @change="onFileChange" />
</label>
      </div>
    </dialog>
    <dialog ref="photoDialog" class="photo-dialog" aria-labelledby="photo-preview-heading" @close="previewPhoto = null">
      <div class="photo-dialog-heading">
<h2 id="photo-preview-heading">第 {{ previewPhoto?.number }} 张照片</h2>
<button type="button" class="btn btn-secondary btn-sm" @click="photoDialog?.close()">关闭预览</button>
</div>
      <img v-if="previewPhoto" class="photo-full" :src="previewPhoto.url" :alt="`第 ${previewPhoto.number} 张作业照片预览`" />
    </dialog>


  </section>
</template>
<style scoped>

.student-status.is-failed { color: #9f3c36; background: #fff0ef; }

.student-alert-review { color: #765d24; border-color: #ead9a9; background: #fffaf0; }

.student-upload-box { width: 100%; box-sizing: border-box; }

.photo-queue-heading { display: flex; justify-content: space-between; gap: 16px; width: 100%; color: #294a67; }

.photo-queue-heading span { font-size: .85rem; white-space: nowrap; }

.photo-add-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }

.student-file-picker:focus-within { outline: 2px solid #2563eb; outline-offset: 3px; }

.student-file-picker.is-disabled { opacity: .5; cursor: not-allowed; }

.photo-queue { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; width: 100%; list-style: none; padding: 0; margin: 4px 0; }

.photo-item { min-width: 0; padding: 7px; border: 1px solid #d5e1eb; border-radius: 9px; background: #fff; }

.photo-thumbnail { display: block; width: 100%; padding: 0; border: 0; background: #eef3f7; color: #315f83; border-radius: 5px; overflow: hidden; cursor: zoom-in; }

.photo-thumbnail img { display: block; width: 100%; height: 140px; object-fit: contain; }

.photo-thumbnail span { display: block; padding: 6px; font-size: .75rem; }

.photo-name { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin: 7px 0; font-size: .75rem; color: #576c7e; }

.photo-controls { display: flex; flex-wrap: wrap; gap: 4px; }

.photo-controls button { flex: 1; min-height: 34px; padding: 4px; border: 1px solid #d5e1eb; border-radius: 5px; background: #fff; color: #315f83; cursor: pointer; }

.photo-controls button:disabled { opacity: .4; cursor: not-allowed; }

.photo-error { margin: 0; color: #a33131; font-size: .85rem; }

.photo-dialog { width: min(680px, calc(100vw - 32px)); box-sizing: border-box; max-height: 90dvh; padding: 20px; border: 1px solid #d5e1eb; border-radius: 14px; color: #294a67; }

.photo-dialog::backdrop { background: rgb(15 23 42 / 65%); }

.photo-dialog-heading { display: flex; align-items: center; justify-content: space-between; gap: 15px; margin-bottom: 12px; }

.photo-dialog-heading h2 { font-size: 1.2rem; margin: 0; }

.camera-video { display: block; width: 100%; max-height: 55dvh; min-height: 160px; margin: 12px 0; background: #0f172a; border-radius: 8px; }

.photo-dialog .photo-add-actions { margin-top: 14px; }

.photo-full { display: block; max-width: 100%; max-height: 70dvh; margin: auto; object-fit: contain; }


.submission{padding:22px;border:1px solid #b5d0c3;background:#fbfdfb;border-radius:16px;margin:18px 0}
.submission-header{display:flex;justify-content:space-between;gap:12px;align-items:center}
.submission-header p{font-size:12px;color:#527365;margin:0 0 8px}
.submission-header h2{font-size:19px;margin:0}
.student-upload-box{display:grid;justify-items:start;gap:12px;background:transparent;padding:16px 0 0;margin:0}
.photo-dialog .muted,.student-upload-box .muted{font-size:13px;line-height:1.7;margin:0;color:#62796d}
.student-file-picker{position:relative;display:inline-flex;align-items:center;min-height:40px;padding:0 12px;border:1px solid #cadcd1;border-radius:8px;background:#fff;color:#365d49;cursor:pointer}
.student-file-picker input{position:absolute;opacity:0;width:1px;height:1px;pointer-events:none}
.btn-primary{background:#185d49;border-color:#185d49}
.photo-queue{grid-template-columns:repeat(auto-fill,minmax(145px,1fr))}

</style>
