const api = require("../../../utils/api");
const auth = require("../../../utils/auth");

Page({
  data: {
    currentUser: null,
    result: null,
    studentName: "",
    loading: true,
    errorMessage: ""
  },

  onLoad: function (options) {
    this.assignmentId = Number(options.assignment_id);
    this.studentId = Number(options.student_id);
  },

  onShow: function () {
    if (auth.guardRole(this, "teacher")) this.loadResult();
  },

  loadResult: function () {
    api.teacherStudentResult(this.assignmentId, this.studentId).then(function (result) {
      const rows = (result.results || []).map(function (row) {
        row.outcome = row.result === "correct" ? "正确"
          : row.result === "partial" ? "部分正确"
            : row.result === "wrong" ? "错误" : row.result;
        row.outcomeClass = row.result === "correct" ? "result-correct"
          : row.result === "wrong" ? "result-wrong" : "result-partial";
        return row;
      });
      result.results = rows;
      this.setData({ result: result, loading: false });
    }.bind(this)).catch(function (error) {
      this.setData({ loading: false, errorMessage: error.message || "无法查看该学生结果" });
    }.bind(this));
  }
});
