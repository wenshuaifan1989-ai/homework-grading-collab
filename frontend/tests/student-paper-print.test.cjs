const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const ts = require(path.join(root, 'node_modules/typescript'));
const source = fs.readFileSync(path.join(root, 'src/student/paperPrint.ts'), 'utf8');
const moduleInstance = { exports: {} };
vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText, { module: moduleInstance, exports: moduleInstance.exports, Blob, URL, Uint8Array, Set, Number, Error });
const { resolvePrintableAssignment, detectPaperBlob, safePaperFilename, createPaperDocumentLoader } = moduleInstance.exports;
const student = { student_id: 91, status: 'active', classes: [{ class_id: 41, status: 'active' }] };
const assignment = { id: 77, student_id: 91, class_id: 41, status: 'published', assignment_mode: 'uniform_mixed', title: '合成数学作业', original_format: 'pdf', submitted: false };
const pdf = () => new Blob(['%PDF-1.7\nsynthetic paper'], { type: 'application/pdf' });

test('printing requires one active learner, the authorized assignment, and its active class', () => {
  for (const requested of ['', '0', '-77', '77<script>', '9007199254740993']) assert.throws(() => resolvePrintableAssignment([student], [assignment], requested));
  assert.throws(() => resolvePrintableAssignment([], [assignment], '77'), /尚未绑定/);
  assert.throws(() => resolvePrintableAssignment([student, { ...student, student_id: 92 }], [assignment], '77'), /多个学生/);
  assert.throws(() => resolvePrintableAssignment([student], [], '77'), /没有这份作业/);
  assert.throws(() => resolvePrintableAssignment([student], [{ ...assignment, student_id: 92 }], '77'), /归属信息/);
  assert.throws(() => resolvePrintableAssignment([{ ...student, classes: [{ class_id: 41, status: 'inactive' }] }], [assignment], '77'), /班级关联/);
  assert.throws(() => resolvePrintableAssignment([student], [{ ...assignment, status: 'draft' }], '77'), /尚未正式发布/);
  assert.throws(() => resolvePrintableAssignment([student], [{ ...assignment, assignment_mode: 'personalized' }], '77'), /暂不提供正式原卷/);
  assert.throws(() => resolvePrintableAssignment([student], [assignment, assignment], '77'), /没有这份作业/);
});

test('submission and pending review leave the published original paper printable', () => {
  for (const task_status of ['WAIT_REVIEW', 'HOLD_REVIEW', 'SUCCESS']) {
    const published = { ...assignment, submitted: true, task_id: 'synthetic-task', task_status };
    assert.equal(resolvePrintableAssignment([student], [published], '77').assignment, published);
  }
  assert.equal(resolvePrintableAssignment([student, { ...student, status: 'inactive', student_id: 92 }], [assignment], '77').student, student);
});

test('only matching MIME, extension and signature permit PDF or image inline opening', async () => {
  assert.equal(await detectPaperBlob(pdf(), 'pdf'), 'pdf');
  assert.equal(await detectPaperBlob(new Blob([new Uint8Array([137,80,78,71,13,10,26,10,0])], { type: 'image/png' }), '.png'), 'image');
  assert.equal(await detectPaperBlob(new Blob([new Uint8Array([255,216,255,224])], { type: 'image/jpeg' }), 'JPEG'), 'image');
  for (const blob of [new Blob(['<html>not a PDF</html>'], { type: 'application/pdf' }), new Blob(['%PDF-1.7'], { type: 'text/html' }), new Blob(['<svg/>'], { type: 'image/svg+xml' })]) {
    assert.equal(await detectPaperBlob(blob, 'pdf'), 'download');
  }
  assert.equal(await detectPaperBlob(pdf(), 'html'), 'download');
  assert.equal(await detectPaperBlob(pdf(), 'docx'), 'download');
  await assert.rejects(detectPaperBlob(new Blob([]), 'pdf'), /文件为空/);
});

test('original PDF bytes are retained; unsafe formats become attachment-only binary blobs', async () => {
  const created = [], revoked = [];
  const loader = createPaperDocumentLoader({ createObjectURL: blob => { created.push(blob); return 'blob:paper-' + created.length; }, revokeObjectURL: url => revoked.push(url) });
  const original = pdf();
  const ready = await loader.load(async () => original, 'pdf', '合成试卷');
  assert.equal(ready.kind, 'pdf');
  assert.equal(created[0], original);
  const html = new Blob(['<html>attachment only</html>'], { type: 'text/html' });
  const attachment = await loader.load(async () => html, 'html', '测试试卷');
  assert.equal(attachment.kind, 'download');
  assert.equal(attachment.filename, '测试试卷.bin');
  assert.equal(created[1].type, 'application/octet-stream');
  assert.equal(await created[1].text(), await html.text());
  assert.deepEqual(revoked, ['blob:paper-1']);
  loader.dispose();
  assert.deepEqual(revoked, ['blob:paper-1', 'blob:paper-2']);
});

test('retry and unmount discard late responses without leaking or replacing an original file', async () => {
  const created = [], revoked = [];
  const loader = createPaperDocumentLoader({ createObjectURL: blob => { created.push(blob); return 'blob:' + created.length; }, revokeObjectURL: url => revoked.push(url) });
  let resolveOld;
  const old = loader.load(() => new Promise(resolve => { resolveOld = resolve; }), 'pdf', '旧试卷');
  const current = await loader.load(async () => pdf(), 'pdf', '新试卷');
  resolveOld(pdf());
  assert.equal(await old, null);
  assert.equal(current.filename, '新试卷.pdf');
  assert.equal(created.length, 1);
  let resolveLate;
  const late = loader.load(() => new Promise(resolve => { resolveLate = resolve; }), 'pdf', '卸载后的试卷');
  assert.deepEqual(revoked, ['blob:1']);
  loader.dispose(); resolveLate(pdf());
  assert.equal(await late, null);
  assert.equal(created.length, 1);
  assert.equal(await loader.load(async () => { throw Error('should not run'); }, 'pdf', '已关闭'), null);
});

test('failed source requests never retain stale previews and can be retried', async () => {
  const revoked = [];
  const loader = createPaperDocumentLoader({ createObjectURL: () => 'blob:paper', revokeObjectURL: url => revoked.push(url) });
  await loader.load(async () => pdf(), 'pdf', '试卷');
  for (const status of [401, 403, 404, 409]) {
    await assert.rejects(loader.load(async () => { throw Object.assign(Error('synthetic'), { response: { status } }); }, 'pdf', '试卷'), error => error.response.status === status);
  }
  assert.deepEqual(revoked, ['blob:paper']);
  assert.equal((await loader.load(async () => pdf(), 'pdf', '重试试卷')).kind, 'pdf');
  loader.dispose();
});

test('download names cannot carry paths, control characters or executable extensions', () => {
  assert.equal(safePaperFilename('../测试/试卷\u0000', 'PDF'), '_测试_试卷_.pdf');
  assert.equal(safePaperFilename('..', 'svg'), '正式作业试卷.bin');
  assert.equal(safePaperFilename('试卷', 'docx'), '试卷.docx');
});
