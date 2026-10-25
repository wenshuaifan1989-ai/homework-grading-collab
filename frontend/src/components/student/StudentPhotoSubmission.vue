<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { studentApi, type StudentAssignment } from '@/api/student';
import { subjectLabel, taskLabel } from '@/student/workbench';
import { useStudentHandheld } from '@/student/device';
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
const handheld = useStudentHandheld();
const nativeCameraInput = ref<HTMLInputElement | null>(null);
const submissionDialog = ref<HTMLDialogElement | null>(null);
const step = ref<'add' | 'review' | 'receipt'>('add');
const receipt = ref<{ task_id: string; status: string; image_count: number } | null>(null);
const photoAddButton = ref<HTMLButtonElement | null>(null);
const uploadPreviews = ref<string[]>([]);
const uploadError = ref('');
const cameraDialog = ref<HTMLDialogElement | null>(null);
const cameraVideo = ref<HTMLVideoElement | null>(null);
const cameraReady = ref(false);
const cameraBusy = ref(false);
const cameraError = ref('');
const photoDialog = ref<HTMLDialogElement | null>(null);
const reviewDialog = ref<HTMLDialogElement | null>(null);
const previewPhoto = ref<{
    url: string;
    number: number;
} | null>(null);
let cameraStream: MediaStream | null = null;
let cameraSession = 0;
const submissionKey = ref('');
const submitting = ref(false);
// A lost response may still mean a task exists. Preserve that request's exact photos and order.
const queueLocked = computed(() => submitting.value || !!submissionKey.value);
// LAN HTTP trials use the operating system's camera picker; live video needs a secure context.
const liveCameraSupported = computed(() => typeof window === 'undefined' || window.isSecureContext !== false);
const error = ref('');
function clearUploadQueue() {
    uploadPreviews.value.forEach((url) => URL.revokeObjectURL(url));
    uploadPreviews.value = [];
    selectedFiles.value = [];
    submissionKey.value = '';
    uploadError.value = '';
}
function appendPhotos(files: File[]): boolean {
    if (queueLocked.value || receipt.value || !files.length)
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
    if (added && selectedFiles.value.length >= 9 && cameraDialog.value?.open)
        closeCamera();
}
function removePhoto(index: number) {
    if (queueLocked.value || index < 0 || index >= selectedFiles.value.length)
        return;
    URL.revokeObjectURL(uploadPreviews.value[index]);
    selectedFiles.value.splice(index, 1);
    uploadPreviews.value.splice(index, 1);
    if (!selectedFiles.value.length) step.value = 'add';
    submissionKey.value = '';
    uploadError.value = '';
}
function movePhoto(index: number, direction: number) {
    const target = index + direction;
    if (queueLocked.value || index < 0 || index >= selectedFiles.value.length || target < 0 || target >= selectedFiles.value.length)
        return;
    [selectedFiles.value[index], selectedFiles.value[target]] = [selectedFiles.value[target], selectedFiles.value[index]];
    [uploadPreviews.value[index], uploadPreviews.value[target]] = [uploadPreviews.value[target], uploadPreviews.value[index]];
    submissionKey.value = '';
}
function showPhoto(index: number) {
    if (index < 0 || index >= uploadPreviews.value.length) return;
    previewPhoto.value = { url: uploadPreviews.value[index], number: index + 1 };
    photoDialog.value?.showModal();
}
function openPhotoAdd() {
    if (queueLocked.value || receipt.value || selectedFiles.value.length >= 9) return;
    if (handheld.value) { openNativeCamera(); return; }
    void openCamera();
}
function openNativeCamera() {
    if (queueLocked.value || receipt.value || selectedFiles.value.length >= 9) return;
    uploadError.value = '';
    nativeCameraInput.value?.click();
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
    if (queueLocked.value || receipt.value || selectedFiles.value.length >= 9)
        return;
    if (handheld.value) { openNativeCamera(); return; }
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
    if (!cameraReady.value || cameraBusy.value || queueLocked.value)
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
        if (appendPhotos([new File([blob], `作业照片-${Date.now()}-${selectedFiles.value.length + 1}.jpg`, { type: 'image/jpeg' })])) {
            if (selectedFiles.value.length >= 9) closeCamera();
        }
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
    if (step.value !== 'review' || receipt.value || submitting.value)
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
        receipt.value = {
            task_id: data.data.task_id,
            status: data.data.status || 'PENDING',
            image_count: Number.isInteger(data.data.image_count) && data.data.image_count > 0 ? data.data.image_count : selectedFiles.value.length,
        };
        reviewDialog.value?.close();
        clearUploadQueue();
        step.value = 'receipt';
        emit('submitted', receipt.value);
        await nextTick();
        document.getElementById('photo-receipt-heading')?.focus();
    }
    catch (requestError: any) {
        error.value = requestError.response?.data?.detail || requestError.response?.data?.message || requestError.message || '提交失败，请保留照片后重试。';
    }
    finally {
        submitting.value = false;
    }
}
async function reviewPhotos() {
    if (!selectedFiles.value.length || submitting.value) return;
    if (cameraDialog.value?.open) closeCamera();
    step.value = 'review';
    await nextTick();
    reviewDialog.value?.showModal();
}
function backToPhotos() {
    if (queueLocked.value) return;
    reviewDialog.value?.close();
    step.value = 'add';
}
function requestClose() { emit('cancel'); }
function focus() { submissionDialog.value?.focus(); }
defineExpose({ hasDraft: computed(() => selectedFiles.value.length > 0), busy: submitting, unresolved: computed(() => !!submissionKey.value && !submitting.value), focus });
watch(handheld, (value) => {
    if (!value) return;
    closeCamera();
});
onMounted(() => { submissionDialog.value?.showModal(); });
onBeforeUnmount(() => { reviewDialog.value?.close(); submissionDialog.value?.close(); cameraDialog.value?.close(); photoDialog.value?.close(); stopCamera(); clearUploadQueue(); });
</script>
<template>
  <dialog ref="submissionDialog" class="submission" aria-labelledby="submission-heading" tabindex="-1" @cancel.prevent="requestClose">
    <header class="submission-header">
<div>
<p>一次提交整份作业</p>
<h2 id="submission-heading">{{ assignment.title }}</h2>
<p class="submission-context">{{ subjectLabel(assignment.subject) }} · {{ assignment.class_name || '班级信息待核对' }}</p>
</div>
<button type="button" class="btn btn-secondary btn-sm" :disabled="submitting" @click="requestClose">关闭提交</button>
</header>
    <ol class="submission-steps" aria-label="作业提交流程">
      <li :aria-current="step === 'add' ? 'step' : undefined" :class="{ active: step === 'add' }">1 添加照片</li>
      <li :aria-current="step === 'review' ? 'step' : undefined" :class="{ active: step === 'review' }">2 提交前预览</li>
      <li :aria-current="step === 'receipt' ? 'step' : undefined" :class="{ active: step === 'receipt' }">3 提交回执</li>
    </ol>
    <section v-if="receipt" class="submission-receipt" aria-labelledby="photo-receipt-heading">
      <h3 id="photo-receipt-heading" tabindex="-1">整份作业已收到</h3>
      <p>本次回执：已收到 {{ receipt.image_count }} 张作业照片。</p>
      <p>任务编号：<strong class="receipt-id">{{ receipt.task_id }}</strong></p>
      <p>{{ receipt.status === 'SUCCESS' ? '已收到处理状态，请关闭后查看可信批改反馈。' : `${taskLabel(receipt.status)}。` }}无需重复提交。</p>
      <button type="button" class="btn btn-primary" @click="requestClose">{{ handheld ? '继续提交其他作业' : '完成，返回作业清单' }}</button>
    </section>
    <template v-else>
    <p v-if="error" class="photo-error" role="alert">{{ error }}</p>
    <div class="student-upload-box">

            <div class="photo-queue-heading">
<strong>{{ step === 'review' ? '提交前，请再看一遍整份作业' : '准备作业照片' }}</strong>
<span aria-live="polite">{{ selectedFiles.length }} / 9 张</span>
</div>
            <p class="muted">{{ step === 'review' ? '下面是即将提交的全部照片。请留意有无漏拍、模糊或顺序不对；点缩略图可看原图。无需逐张确认，看完即可提交。' : '拍清整页，按页码连续添加 1–9 张；先整体预览，再一次提交。' }}</p>
            <div v-if="step === 'add'" class="photo-add-actions">
              <button v-if="handheld" ref="photoAddButton" type="button" class="btn btn-primary camera-picker" :disabled="queueLocked || selectedFiles.length >= 9" @click="openNativeCamera">{{ selectedFiles.length ? '继续拍照添加' : '拍照添加' }}</button>
              <button v-else-if="liveCameraSupported" ref="photoAddButton" type="button" class="btn btn-primary" :disabled="queueLocked || selectedFiles.length >= 9" @click="openPhotoAdd">拍照添加</button>
              <label v-else class="student-file-picker camera-picker" :class="{ 'is-disabled': queueLocked || selectedFiles.length >= 9 }">本机拍照 / 选择照片<input aria-label="使用本机系统相机拍作业" type="file" accept="image/jpeg,image/png,image/gif,image/bmp" capture="environment" :disabled="queueLocked || selectedFiles.length >= 9" @change="onFileChange" /></label>
              <label class="student-file-picker" :class="{ 'is-disabled': queueLocked || selectedFiles.length >= 9 }">从相册选择<input aria-label="从相册选择作业照片" type="file" accept="image/jpeg,image/png,image/gif,image/bmp" multiple :disabled="queueLocked || selectedFiles.length >= 9" @change="onFileChange" />
</label>
              <input v-if="handheld" ref="nativeCameraInput" class="native-camera-input" aria-label="使用手机后置相机拍作业" type="file" accept="image/jpeg,image/png,image/gif,image/bmp" capture="environment" tabindex="-1" :disabled="queueLocked || selectedFiles.length >= 9" @change="onFileChange" />
            </div>
            <p v-if="handheld && step === 'add'" class="muted">直接打开手机相机，拍完一页可继续添加；也可从相册多选。相机无法使用时，请从相册选择。</p>
            <p v-if="uploadError" class="photo-error" role="alert">{{ uploadError }}</p>
            <p v-if="submissionKey && !submitting" class="retry-notice" role="status">尚未确认提交结果，照片与顺序已锁定。请保留本页，用原照片重试；若持续失败，请联系老师核实，避免重复提交。</p>
            <ol v-if="selectedFiles.length" class="photo-queue" aria-label="待提交作业照片">
              <li v-for="(file, index) in selectedFiles" :key="uploadPreviews[index]" class="photo-item">
                <button type="button" class="photo-thumbnail" :aria-label="`预览第 ${index + 1} 张照片`" @click="showPhoto(index)">
<img :src="uploadPreviews[index]" :alt="`第 ${index + 1} 张作业照片`" />
<span>第 {{ index + 1 }} 页 · 点击放大</span>
</button>
                <span class="photo-name" :title="file.name">{{ file.name }}</span>
                <div class="photo-controls">
                  <button type="button" :aria-label="`前移第 ${index + 1} 张照片`" :disabled="queueLocked || index === 0" @click="movePhoto(index, -1)">前移</button>
                  <button type="button" :aria-label="`后移第 ${index + 1} 张照片`" :disabled="queueLocked || index === selectedFiles.length - 1" @click="movePhoto(index, 1)">后移</button>
                  <button type="button" :aria-label="`删除第 ${index + 1} 张照片`" :disabled="queueLocked" @click="removePhoto(index)">删除</button>
                </div>
              </li>
            </ol>
            <p v-else class="muted">还没有添加照片。支持 JPG、PNG、GIF、BMP，每张不超过 10MB。</p>
            <div class="submission-actions">
              <button v-if="step === 'add'" type="button" class="btn btn-primary" :disabled="!selectedFiles.length || queueLocked" @click="reviewPhotos">提交作业 · 先预览 {{ selectedFiles.length }} 张</button>
              <template v-else>
                <button type="button" class="btn btn-secondary" :disabled="queueLocked" @click="backToPhotos">返回调整照片</button>
                <button type="button" class="btn btn-primary" :disabled="submitting || !selectedFiles.length" @click="submitAssignment">{{ submitting ? '提交中…' : `${submissionKey ? '用原照片重试' : '确认提交'} ${selectedFiles.length} 张图片` }}</button>
              </template>
            </div>
    </div>
    </template>
    <dialog ref="reviewDialog" class="review-dialog" aria-labelledby="final-review-heading" @cancel.prevent="backToPhotos">
      <p class="review-eyebrow">提交前再看一遍</p>
      <h2 id="final-review-heading">整份作业 · {{ selectedFiles.length }} 张</h2>
      <p>这里是本次准备上传的全部照片。检查是否漏拍、模糊或页序有误；点任意一张可查看原图。无需逐张打勾。</p>
      <ol class="review-grid" aria-label="本次提交的全部照片缩略图">
        <li v-for="(url,index) in uploadPreviews" :key="url">
          <button type="button" :aria-label="`查看第 ${index+1} 张原图`" @click="showPhoto(index)">
            <img :src="url" :alt="`第 ${index+1} 张作业照片`" />
            <span>第 {{ index+1 }} 张 · 看原图</span>
          </button>
        </li>
      </ol>
      <p v-if="error" class="photo-error" role="alert">{{ error }}</p>
      <p v-if="submissionKey && !submitting" class="retry-notice" role="status">结果尚未确认，请保留原照片并用同一提交键重试。</p>
      <div class="submission-actions">
        <button type="button" class="btn btn-secondary" :disabled="queueLocked" @click="backToPhotos">返回补拍或调整顺序</button>
        <button type="button" class="btn btn-primary" :disabled="submitting || !selectedFiles.length" @click="submitAssignment">{{ submitting ? '正在提交…' : submissionKey ? '用原照片重试' : '确认提交' }}</button>
      </div>
    </dialog>
    <dialog ref="cameraDialog" class="photo-dialog" aria-labelledby="camera-heading" @close="stopCamera" @cancel="stopCamera">
      <div class="photo-dialog-heading">
<h2 id="camera-heading">拍摄作业</h2>
<button type="button" class="btn btn-secondary btn-sm" @click="closeCamera">关闭相机</button>
</div>
      <p class="muted">将整页放入画面，保持光线充足。可连续拍到 9 张，拍完后整体预览。</p>
      <video ref="cameraVideo" autoplay muted playsinline class="camera-video" aria-label="作业拍摄画面">
</video>
      <p v-if="cameraError" class="photo-error" role="alert">{{ cameraError }}</p>
      <p v-else-if="!cameraReady" role="status">正在打开相机，请按浏览器提示允许使用摄像头…</p>
      <div class="photo-add-actions">
        <button type="button" class="btn btn-primary" :disabled="!cameraReady || cameraBusy || selectedFiles.length>=9" @click="takePhoto">{{ cameraBusy ? '正在保存…' : `拍照并添加（${selectedFiles.length}/9）` }}</button>
        <label class="student-file-picker">系统相机 / 选择照片<input aria-label="系统相机或选择照片" type="file" accept="image/jpeg,image/png,image/gif,image/bmp" capture="environment" :disabled="cameraBusy" @change="onFileChange" />
</label>
      </div>
      <p class="muted" aria-live="polite">已拍/选 {{ selectedFiles.length }} 张；可以继续拍，或结束拍摄查看全部。</p>
      <div v-if="selectedFiles.length" class="camera-strip" aria-label="已拍摄照片">
        <button v-for="(url,index) in uploadPreviews" :key="url" type="button" :aria-label="`看第 ${index+1} 张原图`" @click="showPhoto(index)"><img :src="url" :alt="`第 ${index+1} 张照片缩略图`" /></button>
      </div>
      <button v-if="selectedFiles.length" type="button" class="btn btn-secondary" @click="closeCamera">拍完了，查看全部照片</button>
    </dialog>
    <dialog ref="photoDialog" class="photo-dialog" aria-labelledby="photo-preview-heading" @close="previewPhoto = null">
      <div class="photo-dialog-heading">
<h2 id="photo-preview-heading">第 {{ previewPhoto?.number }} 张照片</h2>
<button type="button" class="btn btn-secondary btn-sm" @click="photoDialog?.close()">关闭预览</button>
</div>
      <img v-if="previewPhoto" class="photo-full" :src="previewPhoto.url" :alt="`第 ${previewPhoto.number} 张作业照片预览`" />
    </dialog>


  </dialog>
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
.student-file-picker.camera-picker{background:#185d49;color:white;border-color:#185d49;font-weight:600}

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
.retry-notice{margin:0;padding:12px;border:1px solid #e6d6ab;border-radius:8px;background:#fff8e8;color:#806633;font-size:13px;line-height:1.8}

.photo-dialog { width: min(680px, calc(100vw - 32px)); box-sizing: border-box; max-height: 90dvh; padding: 20px; border: 1px solid #d5e1eb; border-radius: 14px; color: #294a67; margin: auto; }

.photo-dialog::backdrop { background: rgb(15 23 42 / 65%); }

.photo-dialog-heading { display: flex; align-items: center; justify-content: space-between; gap: 15px; margin-bottom: 12px; }

.photo-dialog-heading h2 { font-size: 1.2rem; margin: 0; }

.camera-video { display: block; width: 100%; max-height: 55dvh; min-height: 160px; margin: 12px 0; background: #0f172a; border-radius: 8px; }

.photo-dialog .photo-add-actions { margin-top: 14px; }

.photo-full { display: block; max-width: 100%; max-height: 70dvh; margin: auto; object-fit: contain; }
.review-dialog{width:min(760px,calc(100vw - 24px));max-height:90dvh;overflow:auto;box-sizing:border-box;padding:22px;border:1px solid #bad4c0;border-radius:16px;color:#294a39}
.review-dialog::backdrop{background:rgb(17 35 24 / 70%)}.review-dialog h2{font-size:20px;margin:0}.review-dialog p{font-size:13px;line-height:1.7}.review-eyebrow{color:#4a795c;letter-spacing:.05em}
.review-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;list-style:none;padding:0;margin:16px 0}
.review-grid li{min-width:0}.review-grid button{display:grid;justify-items:center;width:100%;padding:5px;border:1px solid #d4e3d7;border-radius:8px;background:#f9fbf9;color:#365d49;cursor:zoom-in}
.review-grid img{width:100%;height:clamp(72px,12vh,148px);object-fit:contain}.review-grid span{font-size:11px;padding:5px 0}
.camera-strip{display:flex;gap:8px;overflow-x:auto;padding:8px 0}.camera-strip button{flex:none;width:72px;height:72px;padding:3px;background:#fff;border:1px solid #c5d8ca;border-radius:6px}.camera-strip img{width:100%;height:100%;object-fit:contain}


.submission{padding:24px;border:1px solid #b5d0c3;background:#fbfdfb;border-radius:16px;width:min(780px,calc(100vw - 32px));max-height:90dvh;box-sizing:border-box;color:#263d32;overflow:auto;margin:auto}
.submission::backdrop{background:rgb(19 35 26 / 65%)}
.submission:focus{outline:none}
.submission-steps{display:flex;gap:10px;list-style:none;padding:0;margin:20px 0;flex-wrap:wrap;font-size:12px;color:#788b80}
.submission-steps li{padding:7px 10px;border-radius:7px;background:#eef2ec}
.submission-steps .active{background:#dfede3;color:#185d49;font-weight:600}
.submission-actions{display:flex;flex-wrap:wrap;gap:10px;width:100%;padding-top:8px}
.submission-receipt{padding:14px;border:1px solid #d5e7d7;border-radius:10px;background:#eef7ed;font-size:14px;line-height:1.8}
.submission-receipt h3{margin:0 0 12px;font-size:19px}
.receipt-id{overflow-wrap:anywhere}
.submission-header{display:flex;justify-content:space-between;gap:12px;align-items:center}
.submission-header p{font-size:12px;color:#527365;margin:0 0 8px}
.submission-header h2{font-size:19px;margin:0}
.submission-header .submission-context{margin:8px 0 0;line-height:1.6}
.student-upload-box{display:grid;justify-items:start;gap:12px;background:transparent;padding:16px 0 0;margin:0}
.photo-dialog .muted,.student-upload-box .muted{font-size:13px;line-height:1.7;margin:0;color:#62796d}
.student-file-picker{position:relative;display:inline-flex;align-items:center;min-height:40px;padding:0 12px;border:1px solid #cadcd1;border-radius:8px;background:#fff;color:#365d49;cursor:pointer}
.student-file-picker input{position:absolute;opacity:0;width:1px;height:1px;pointer-events:none}
.btn-primary{background:#185d49;border-color:#185d49}
.photo-queue{grid-template-columns:repeat(auto-fill,minmax(145px,1fr))}
.native-camera-input{position:absolute;width:1px;height:1px;opacity:0;pointer-events:none;overflow:hidden}
@media(max-width:700px){
  .submission,.photo-dialog,.review-dialog{width:calc(100vw - 16px);max-width:100%;max-height:calc(100dvh - 16px);padding:16px 12px;padding-bottom:max(16px,env(safe-area-inset-bottom));overflow:auto;overscroll-behavior:contain}
  .submission button,.photo-dialog button,.review-dialog button,.student-file-picker{min-height:44px;touch-action:manipulation}
  .submission-header,.photo-dialog-heading{align-items:flex-start;gap:10px}
  .submission-header>div{min-width:0;overflow-wrap:anywhere}
  .submission-header>.btn,.photo-dialog-heading>.btn{flex-shrink:0}
  .submission-header h2{font-size:18px;line-height:1.5}
  .submission-steps{gap:5px;font-size:11px;margin:16px 0}
  .submission-steps li{padding:8px 6px}
  .photo-add-actions{width:100%;align-items:stretch}
  .photo-add-actions>.btn,.photo-add-actions>.student-file-picker{flex:1;justify-content:center;text-align:center}
  .photo-queue{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
  .photo-thumbnail img{height:120px}
  .photo-controls{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}
  .photo-controls button{min-width:44px}
  .photo-controls button:last-child{grid-column:1/-1}
  .submission-actions>.btn{flex:1 1 100%;white-space:normal;line-height:1.5}
  .review-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:6px}
  .review-grid span{font-size:10px}
}

</style>
