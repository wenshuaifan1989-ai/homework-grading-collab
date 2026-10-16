const api = require("../../../utils/api");
const auth = require("../../../utils/auth");
const display = require("../../../utils/display");

Page({
  data: {
    currentUser: null,
    classId: 0,
    className: "",
    assignments: [],
    loading: true
  },

  onLoad: function (options) {
    this.classId = Number(options.id);
    const classroom = wx.getStorageSync("selected_class") || {};
    this.setData({ classId: this.classId, className: classroom.name || "" });
  },

  onShow: function () {
    if (auth.guardRole(this, "teacher")) this.loadAssignments();
  },

  onPullDownRefresh: function () {
    this.loadAssignments().then(function () { wx.stopPullDownRefresh(); });
  },

  loadAssignments: function () {
    this.setData({ loading: true });
    return api.teacherAssignments(this.classId).then(function (items) {
      const assignments = (items || []).map(function (item) {
        item.dueLabel = display.dateLabel(item.due_at);
        return item;
      });
      this.setData({ assignments: assignments, loading: false });
    }.bind(this)).catch(function (error) {
      this.setData({ loading: false });
      wx.showToast({ title: error.message || "作业加载失败", icon: "none" });
    }.bind(this));
  },

  createAssignment: function () {
    wx.navigateTo({
      url: "/pages/teacher/assignment-form/assignment-form?class_id=" + this.classId
    });
  },

  openSubmissions: function (event) {
    const id = event.currentTarget.dataset.id;
    wx.navigateTo({ url: "/pages/teacher/submissions/submissions?id=" + id });
  }
});
