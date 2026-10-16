const api = require("../../../utils/api");
const auth = require("../../../utils/auth");

Page({
  data: {
    currentUser: null,
    classes: [],
    loading: true
  },

  onShow: function () {
    if (auth.guardRole(this, "teacher")) this.loadClasses();
  },

  onPullDownRefresh: function () {
    this.loadClasses().then(function () { wx.stopPullDownRefresh(); });
  },

  loadClasses: function () {
    this.setData({ loading: true });
    return api.teacherClasses().then(function (classes) {
      this.setData({ classes: classes || [], loading: false });
    }.bind(this)).catch(function (error) {
      this.setData({ loading: false });
      wx.showToast({ title: error.message || "班级加载失败", icon: "none" });
    }.bind(this));
  },

  openDashboard: function (event) {
    const id = Number(event.currentTarget.dataset.id);
    const item = this.data.classes.find(function (row) {
      return Number(row.id) === id;
    });
    if (!item) return;
    wx.setStorageSync("selected_class", item);
    wx.navigateTo({ url: "/pages/teacher/dashboard/dashboard?id=" + item.id });
  },

  openAssignments: function (event) {
    const id = Number(event.currentTarget.dataset.id);
    if (!id) return;
    wx.navigateTo({ url: "/pages/teacher/assignments/assignments?id=" + id });
  },

  openRoster: function (event) {
    const id = Number(event.currentTarget.dataset.id);
    if (!id) return;
    const classroom = this.data.classes.find(function (row) { return Number(row.id) === id; });
    if (classroom) wx.setStorageSync("selected_class", classroom);
    wx.navigateTo({ url: "/pages/teacher/roster/roster?id=" + id });
  },

  openManagement: function (event) {
    const id = Number(event.currentTarget.dataset.id);
    if (!id) return;
    const classroom = this.data.classes.find(function (row) { return Number(row.id) === id; });
    if (classroom) wx.setStorageSync("selected_class", classroom);
    wx.navigateTo({ url: "/pages/teacher/class-relations/class-relations?id=" + id });
  },

  createClass: function () {
    wx.navigateTo({ url: "/pages/teacher/class-form/class-form" });
  },

  copyInvite: function (event) {
    const code = event.currentTarget.dataset.code;
    wx.setClipboardData({ data: code });
  },

  acceptTeacherInvite: function () {
    wx.showModal({
      title: "接受教师邀请",
      editable: true,
      placeholderText: "输入教师邀请码",
      success: function (codeResult) {
        if (!codeResult.confirm || !codeResult.content.trim()) return;
        wx.showModal({
          title: "设置承担学科",
          content: "支持用逗号分隔学科代码，如 math,english；留空表示不限定学科。",
          editable: true,
          placeholderText: "math,english",
          success: function (subjectResult) {
            if (!subjectResult.confirm) return;
            const subjectCodes = (subjectResult.content || "").split(/[,，]/)
              .map(function (value) { return value.trim(); }).filter(Boolean);
            api.claimContract(codeResult.content.trim(), { subject_codes: subjectCodes })
              .then(function (data) {
                wx.showToast({ title: data.already_joined ? "已是本班教师" : "已加入班级", icon: "success" });
                this.loadClasses();
              }.bind(this))
              .catch(function (error) { wx.showToast({ title: error.message || "邀请无效或已过期", icon: "none" }); });
          }.bind(this)
        });
      }.bind(this)
    });
  }
});
