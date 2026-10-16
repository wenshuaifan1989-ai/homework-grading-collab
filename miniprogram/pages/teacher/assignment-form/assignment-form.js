const api = require("../../../utils/api");
const auth = require("../../../utils/auth");

function pad(number) {
  return number < 10 ? "0" + number : String(number);
}

Page({
  data: {
    currentUser: null,
    classId: 0,
    className: "",
    title: "",
    description: "",
    subjectOptions: [
      { label: "数学", value: "math" },
      { label: "语文", value: "chinese" },
      { label: "英语", value: "english" },
      { label: "物理", value: "physics" },
      { label: "化学", value: "chemistry" }
    ],
    gradeOptions: Array.from({ length: 9 }, function (_, index) {
      return { label: "年级 " + (index + 1), value: "grade" + (index + 1) };
    }),
    subjectIndex: 0,
    gradeIndex: 6,
    assignmentDate: "",
    dueDate: "",
    dueTime: "23:59",
    saving: false
  },

  onLoad: function (options) {
    const classId = Number(options.class_id);
    const classroom = wx.getStorageSync("selected_class") || {};
    const now = new Date();
    this.setData({
      classId: classId,
      className: classroom.name || "",
      assignmentDate: now.getFullYear() + "-" + pad(now.getMonth() + 1) + "-" + pad(now.getDate()),
      dueDate: now.getFullYear() + "-" + pad(now.getMonth() + 1) + "-" + pad(now.getDate())
    });
  },

  onShow: function () {
    auth.guardRole(this, "teacher");
  },

  onTitleInput: function (event) {
    this.setData({ title: event.detail.value || "" });
  },

  onDescriptionInput: function (event) {
    this.setData({ description: event.detail.value || "" });
  },

  onSubjectChange: function (event) {
    this.setData({ subjectIndex: Number(event.detail.value) });
  },

  onGradeChange: function (event) {
    this.setData({ gradeIndex: Number(event.detail.value) });
  },

  onDueDateChange: function (event) {
    this.setData({ dueDate: event.detail.value });
  },

  onAssignmentDateChange: function (event) {
    this.setData({ assignmentDate: event.detail.value });
  },

  onDueTimeChange: function (event) {
    this.setData({ dueTime: event.detail.value });
  },

  publish: function () {
    const title = this.data.title.trim();
    if (!title) {
      wx.showToast({ title: "请填写作业标题", icon: "none" });
      return;
    }
    if (this.data.saving) return;
    const subject = this.data.subjectOptions[this.data.subjectIndex].value;
    const grade = this.data.gradeOptions[this.data.gradeIndex].value;
    const dueAt = this.data.dueDate + "T" + this.data.dueTime + ":00";
    this.setData({ saving: true });
    api.createAssignment(this.data.classId, {
      title: title,
      description: this.data.description.trim(),
      subject: subject,
      grade: grade,
      assignment_date: this.data.assignmentDate,
      due_at: dueAt
    }).then(function () {
      wx.showToast({ title: "作业已发布", icon: "success" });
      setTimeout(function () { wx.navigateBack({ delta: 1 }); }, 550);
    }).catch(function (error) {
      wx.showToast({ title: error.message || "发布失败", icon: "none" });
    }).then(function () {
      this.setData({ saving: false });
    }.bind(this));
  }
});
