const api = require("../../../utils/api");
const auth = require("../../../utils/auth");

Page({
  data: { assignmentId: 0, questionKey: "", detail: null, loading: true, errorMessage: "" },

  onLoad: function (options) {
    this.assignmentId = Number(options.assignment_id);
    this.questionKey = decodeURIComponent(options.question_key || "");
    this.setData({ assignmentId: this.assignmentId, questionKey: this.questionKey });
  },

  onShow: function () {
    if (auth.guardRole(this, "teacher")) this.loadDetail();
  },

  loadDetail: function () {
    api.questionStudents(this.assignmentId, this.questionKey).then(function (detail) {
      this.setData({ detail: detail, loading: false });
    }.bind(this)).catch(function (error) {
      this.setData({ loading: false, errorMessage: error.message || "题目明细加载失败" });
    }.bind(this));
  },

  openStudent: function (event) {
    const studentId = event.currentTarget.dataset.student;
    if (!studentId) return;
    wx.navigateTo({
      url: "/pages/teacher/result/result?assignment_id=" + this.assignmentId + "&student_id=" + studentId
    });
  }
});
