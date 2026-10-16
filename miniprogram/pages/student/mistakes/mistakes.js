const api = require("../../../utils/api");
const auth = require("../../../utils/auth");

Page({
  data: {
    currentUser: null,
    students: [],
    selectedStudentId: 0,
    selectedStudentName: "",
    mistakes: [],
    loading: false,
    errorMessage: "",
    notice: ""
  },

  onShow: function () {
    if (!auth.guardRole(this, "student")) return;
    this.loadStudents();
  },

  loadStudents: function () {
    this.setData({ loading: true, errorMessage: "" });
    return api.myStudents().then(function (students) {
      students = (students || []).filter(function (item) { return item.status === "active"; });
      const saved = Number(wx.getStorageSync("active_student_id") || 0);
      const selected = students.some(function (item) { return item.student_id === saved; })
        ? saved : (students.length === 1 ? students[0].student_id : 0);
      const current = students.find(function (item) { return item.student_id === selected; });
      this.setData({
        students: students,
        selectedStudentId: selected,
        selectedStudentName: current ? current.name : "",
        loading: false
      });
      if (selected) {
        wx.setStorageSync("active_student_id", selected);
        return this.loadMistakes();
      }
      this.setData({ mistakes: [] });
    }.bind(this)).catch(function (error) {
      this.setData({ loading: false, errorMessage: error.message || "学生身份读取失败" });
    }.bind(this));
  },

  selectStudent: function (event) {
    const id = Number(event.currentTarget.dataset.id || 0);
    const student = this.data.students.find(function (item) { return item.student_id === id; });
    this.setData({ selectedStudentId: id, selectedStudentName: student ? student.name : "" });
    if (id) wx.setStorageSync("active_student_id", id);
    this.loadMistakes();
  },

  openBinding: function () {
    wx.navigateTo({ url: "/pages/student/bind/bind" });
  },

  loadMistakes: function () {
    if (!this.data.selectedStudentId) return Promise.resolve();
    this.setData({ loading: true, errorMessage: "" });
    return api.studentMistakes(this.data.selectedStudentId).then(function (response) {
      const items = (response.items || []).map(function (item) {
        item.expanded = false;
        item.attempts = [];
        item.draft = "";
        if (item.question) item.question.knowledge_points_label = (item.question.knowledge_points || []).join("、");
        return item;
      });
      this.setData({ mistakes: items, loading: false });
    }.bind(this)).catch(function (error) {
      this.setData({ loading: false, errorMessage: error.message || "错题集读取失败" });
    }.bind(this));
  },

  previewImage: function (event) {
    const item = event.currentTarget.dataset.item;
    const kind = event.currentTarget.dataset.kind || "crop";
    const path = kind === "original" ? item.original_url : item.crop_url;
    api.downloadPaperImage(path).then(function (filePath) {
      wx.previewImage({ current: filePath, urls: [filePath] });
    }).catch(function (error) {
      this.setData({ errorMessage: error.message || "题目图片读取失败" });
    }.bind(this));
  },

  onDraftInput: function (event) {
    const id = Number(event.currentTarget.dataset.id);
    const index = this.data.mistakes.findIndex(function (item) { return item.id === id; });
    if (index < 0) return;
    const update = {};
    update["mistakes[" + index + "].draft"] = event.detail.value;
    this.setData(update);
  },

  submitCorrection: function (event) {
    const id = Number(event.currentTarget.dataset.id);
    const item = this.data.mistakes.find(function (row) { return row.id === id; });
    const answer = item ? (item.draft || "").trim() : "";
    if (!answer) {
      wx.showToast({ title: "先输入订正答案", icon: "none" });
      return;
    }
    api.submitCorrection(id, answer).then(function () {
      this.setData({ notice: "订正已提交，教师可在授权班级内复核。", errorMessage: "" });
      return this.loadMistakes();
    }.bind(this)).catch(function (error) {
      this.setData({ errorMessage: error.message || "订正提交失败" });
    }.bind(this));
  },

  markMastered: function (event) {
    const id = Number(event.currentTarget.dataset.id);
    api.markMistakeMastered(id).then(function () {
      this.setData({ notice: "已记录自评掌握；原错题和历史仍保留。", errorMessage: "" });
      return this.loadMistakes();
    }.bind(this)).catch(function (error) {
      this.setData({ errorMessage: error.message || "掌握状态保存失败" });
    }.bind(this));
  },

  toggleHistory: function (event) {
    const id = Number(event.currentTarget.dataset.id);
    const index = this.data.mistakes.findIndex(function (item) { return item.id === id; });
    if (index < 0) return;
    const item = this.data.mistakes[index];
    if (item.expanded) {
      const update = {};
      update["mistakes[" + index + "].expanded"] = false;
      this.setData(update);
      return;
    }
    api.correctionHistory(id).then(function (response) {
      const update = {};
      update["mistakes[" + index + "].attempts"] = response.items || [];
      update["mistakes[" + index + "].expanded"] = true;
      this.setData(update);
    }.bind(this)).catch(function (error) {
      this.setData({ errorMessage: error.message || "订正历史读取失败" });
    }.bind(this));
  }
});
