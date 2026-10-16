const api = require("../../../utils/api");
const auth = require("../../../utils/auth");
const display = require("../../../utils/display");

Page({
  data: {
    currentUser: null,
    assignmentId: 0,
    students: [],
    submittedCount: 0,
    unsubmittedCount: 0,
    loading: true
  },

  onLoad: function (options) {
    this.assignmentId = Number(options.id);
    this.setData({ assignmentId: this.assignmentId });
  },

  onShow: function () {
    if (auth.guardRole(this, "teacher")) this.loadSubmissions();
  },

  onPullDownRefresh: function () {
    this.loadSubmissions().then(function () { wx.stopPullDownRefresh(); });
  },

  loadSubmissions: function () {
    this.setData({ loading: true });
    return api.assignmentSubmissions(this.assignmentId).then(function (items) {
      const students = (items || []).map(function (student) {
        student.statusLabel = student.submitted
          ? display.statusLabel(student.task_status) : "未提交";
        student.submittedAtLabel = display.dateLabel(student.submitted_at);
        student.initial = (student.student_name || "学").slice(0, 1);
        return student;
      });
      this.setData({
        students: students,
        submittedCount: students.filter(function (student) { return student.submitted; }).length,
        unsubmittedCount: students.filter(function (student) { return !student.submitted; }).length,
        loading: false
      });
    }.bind(this)).catch(function (error) {
      this.setData({ loading: false });
      wx.showToast({ title: error.message || "提交情况加载失败", icon: "none" });
    }.bind(this));
  },

  openStudentResult: function (event) {
    const studentId = event.currentTarget.dataset.student;
    if (!studentId) return;
    wx.navigateTo({
      url: "/pages/teacher/result/result?assignment_id=" +
        this.assignmentId + "&student_id=" + studentId
    });
  }
});
