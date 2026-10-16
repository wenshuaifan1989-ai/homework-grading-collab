const http = require("./request");
const multipart = require("./multipart");

module.exports = {
  login: function (phone, password) {
    return http.post("/api/v1/users/login", {
      phone: phone,
      password: password
    }, { auth: false });
  },
  registerStudent: function (phone, password, fullName) {
    return http.post("/api/v1/users/register", {
      phone: phone,
      password: password,
      full_name: fullName
    }, { auth: false });
  },
  myProfile: function () {
    return http.get("/api/v1/users/me");
  },
  wechatLogin: function (code) {
    return http.post("/api/v1/users/wechat-login", { code: code });
  },
  wechatPhone: function (code) {
    return http.post("/api/v1/users/wechat-phone", { code: code });
  },
  updateMyProfile: function (profile) {
    return http.request("/api/v1/users/me/profile", "PATCH", profile);
  },
  myStudents: function () {
    return http.get("/api/v1/students/mine");
  },
  claimContract: function (code, payload) {
    return http.post("/api/v1/contracts/" + encodeURIComponent(code) + "/claim", payload || {});
  },
  createFamilyContract: function (studentId) {
    return http.post("/api/v1/students/" + studentId + "/family-contract", {});
  },
  removeFamilyBinding: function (studentId, userId) {
    return http.post("/api/v1/students/" + studentId + "/family-bindings/" + userId + "/remove", {});
  },
  classRelationRequests: function (classId) {
    return http.get("/api/v1/classes/" + classId + "/relation-requests");
  },
  reviewStudentLeave: function (classId, studentId, approve) {
    return http.post("/api/v1/classes/" + classId + "/students/" + studentId + "/leave-review", { approve: approve });
  },
  reviewFamilyBinding: function (studentId, userId, approve) {
    return http.post("/api/v1/students/" + studentId + "/family-bindings/" + userId + "/review", { approve: approve });
  },
  studentBinding: function () {
    return http.get("/api/v1/students/binding");
  },
  studentAssignments: function (studentId) {
    const suffix = studentId ? "?student_id=" + encodeURIComponent(studentId) : "";
    return http.get("/api/v1/assignments/mine" + suffix);
  },
  homeworkHistory: function () {
    return http.get("/api/v1/homework/list?page=1&page_size=50");
  },
  teacherClasses: function () {
    return http.get("/api/v1/classes/mine");
  },
  classRoster: function (classId) {
    return http.get("/api/v1/classes/" + classId + "/roster");
  },
  addRosterStudent: function (classId, studentName, studentNo) {
    return http.post("/api/v1/classes/" + classId + "/roster", {
      student_name: studentName,
      student_no: studentNo || null
    });
  },
  addRosterBatch: function (classId, lines) {
    return http.post("/api/v1/classes/" + classId + "/roster/batch", { lines: lines });
  },
  unbindRosterStudent: function (classId, rosterId) {
    return http.post("/api/v1/classes/" + classId + "/roster/" + rosterId + "/unbind");
  },
  adminTeachers: function () {
    return http.get("/api/v1/admin/teachers");
  },
  adminCreateTeacher: function (phone, password, fullName) {
    return http.post("/api/v1/admin/teachers", {
      phone: phone,
      password: password,
      full_name: fullName
    });
  },
  adminTeacherStatus: function (teacherId, isActive) {
    return http.post("/api/v1/admin/teachers/" + teacherId + "/status", { is_active: isActive });
  },
  adminClasses: function () {
    return http.get("/api/v1/admin/classes");
  },
  searchSchools: function (query, stage) {
    const params = [];
    if (query) params.push("q=" + encodeURIComponent(query));
    if (stage) params.push("stage=" + encodeURIComponent(stage));
    return http.get("/api/v1/schools" + (params.length ? "?" + params.join("&") : ""));
  },
  createCustomSchool: function (payload) {
    return http.post("/api/v1/schools/custom", payload);
  },
  createClass: function (payload) {
    return http.post("/api/v1/classes", payload);
  },
  createClassContract: function (classId, type, maxUses) {
    return http.post("/api/v1/classes/" + classId + "/contracts", {
      type: type,
      max_uses: maxUses || 1
    });
  },
  classTeachers: function (classId) {
    return http.get("/api/v1/classes/" + classId + "/teachers");
  },
  removeClassTeacher: function (classId, teacherUserId) {
    return http.post("/api/v1/classes/" + classId + "/teachers/" + teacherUserId + "/remove", {});
  },
  leaveClassAsTeacher: function (classId) {
    return http.post("/api/v1/classes/" + classId + "/teachers/leave", {});
  },
  transferClassOwner: function (classId, teacherUserId) {
    return http.post("/api/v1/classes/" + classId + "/owner-transfer", {
      teacher_user_id: teacherUserId
    });
  },
  updateClassStatus: function (classId, status) {
    return http.post("/api/v1/classes/" + classId + "/status", { status: status });
  },
  removeStudentFromClass: function (classId, studentId) {
    return http.post("/api/v1/classes/" + classId + "/students/" + studentId + "/remove", {});
  },
  requestStudentLeave: function (studentId, classId) {
    return http.post("/api/v1/students/" + studentId + "/classes/" + classId + "/leave", {});
  },
  createAssignment: function (classId, payload) {
    return http.post("/api/v1/classes/" + classId + "/assignments", payload);
  },
  teacherAssignments: function (classId) {
    return http.get("/api/v1/classes/" + classId + "/assignments");
  },
  learningTiers: function (classId, subject) {
    return http.get("/api/v1/learning/classes/" + classId + "/tiers?subject=" + encodeURIComponent(subject));
  },
  saveLearningTiers: function (classId, subject, entries) {
    return http.request("/api/v1/learning/classes/" + classId + "/tiers", "PUT", {
      subject: subject,
      entries: entries
    });
  },
  learningVariants: function (assignmentId) {
    return http.get("/api/v1/learning/assignments/" + assignmentId + "/variants");
  },
  saveLearningVariants: function (assignmentId, payload) {
    return http.request("/api/v1/learning/assignments/" + assignmentId + "/variants", "PUT", payload);
  },
  downloadLearningVariant: function (assignmentId, level) {
    return http.download("/api/v1/learning/assignments/" + assignmentId + "/variants/" +
      encodeURIComponent(level) + "/print.pdf");
  },
  classCalendar: function (classId, month) {
    return http.get("/api/v1/classes/" + classId + "/calendar?month=" + encodeURIComponent(month));
  },
  classDailyDashboard: function (classId, date, assignmentId) {
    var path = "/api/v1/classes/" + classId + "/daily-dashboard?date=" + encodeURIComponent(date);
    if (assignmentId) path += "&assignment_id=" + encodeURIComponent(assignmentId);
    return http.get(path);
  },
  questionStudents: function (assignmentId, questionKey) {
    return http.get(
      "/api/v1/assignments/" + assignmentId + "/questions/" + encodeURIComponent(questionKey) + "/students"
    );
  },
  assignmentSubmissions: function (assignmentId) {
    return http.get("/api/v1/assignments/" + assignmentId + "/submissions");
  },
  digitizePaperTask: function (taskId) {
    return http.post("/api/v1/paper/tasks/" + encodeURIComponent(taskId) + "/digitize", {});
  },
  paperTaskAssets: function (taskId) {
    return http.get("/api/v1/paper/tasks/" + encodeURIComponent(taskId) + "/assets");
  },
  reviewPaperSource: function (sourceId, payload) {
    return http.request("/api/v1/paper/sources/" + sourceId + "/review", "PATCH", payload);
  },
  classMistakes: function (classId, studentId) {
    const suffix = studentId ? "?student_id=" + encodeURIComponent(studentId) : "";
    return http.get("/api/v1/paper/classes/" + classId + "/mistakes" + suffix);
  },
  studentMistakes: function (studentId) {
    return http.get("/api/v1/paper/students/" + studentId + "/mistakes");
  },
  correctionHistory: function (mistakeId) {
    return http.get("/api/v1/paper/mistakes/" + mistakeId + "/history");
  },
  submitCorrection: function (mistakeId, answer) {
    return http.post("/api/v1/paper/mistakes/" + mistakeId + "/corrections", { answer: answer });
  },
  markMistakeMastered: function (mistakeId) {
    return http.post("/api/v1/paper/mistakes/" + mistakeId + "/mastery", {});
  },
  reviewCorrection: function (mistakeId, attemptId, accepted, feedback) {
    return http.post(
      "/api/v1/paper/mistakes/" + mistakeId + "/corrections/" + attemptId + "/review",
      { accepted: accepted, feedback: feedback || null }
    );
  },
  downloadPaperImage: function (path) {
    return http.download(path);
  },
  teacherStudentResult: function (assignmentId, studentId) {
    return http.get(
      "/api/v1/assignments/" + assignmentId + "/submissions/" +
      studentId + "/result"
    );
  },
  studentResult: function (taskId) {
    return http.get("/api/v1/homework/result/" + encodeURIComponent(taskId));
  },
  taskStatus: function (taskId) {
    return http.get("/api/v1/homework/status/" + encodeURIComponent(taskId));
  },
  retryHomework: function (taskId) {
    return http.post("/api/v1/homework/retry/" + encodeURIComponent(taskId), {
      confirm_possible_duplicate_charge: true
    });
  },
  submitAssignment: function (files, assignmentId, subject, grade, studentId, idempotencyKey) {
    const fields = {
      student_id: studentId,
      subject: subject,
      grade: grade,
      mode: "vision"
    };
    const normalizedAssignmentId = Number(assignmentId);
    if (Number.isSafeInteger(normalizedAssignmentId) && normalizedAssignmentId > 0) {
      fields.assignment_id = normalizedAssignmentId;
    }
    return multipart.upload("/api/v1/homework/analyze", files, fields, idempotencyKey);
  }
};
