const api = require("../../../utils/api");
const auth = require("../../../utils/auth");

Page({
  data: {
    currentUser: null,
    classId: 0,
    roster: [],
    loading: true,
    batchLines: "",
    isOwner: false
  },

  onLoad: function (options) {
    const classroom = wx.getStorageSync("selected_class") || {};
    this.setData({
      classId: Number(options.id || options.class_id),
      isOwner: classroom.teacher_role === "owner"
    });
  },

  onShow: function () {
    const session = auth.getSession();
    if (!session.token || !session.user || (session.user.role !== "teacher" && session.user.role !== "admin")) {
      wx.reLaunch({ url: "/pages/login/login" });
      return;
    }
    this.setData({ currentUser: session.user });
    this.loadRoster();
  },

  loadRoster: function () {
    this.setData({ loading: true });
    return api.classRoster(this.data.classId).then(function (roster) {
      this.setData({ roster: roster || [], loading: false });
    }.bind(this)).catch(function (error) {
      this.setData({ loading: false });
      wx.showToast({ title: error.message || "名册加载失败", icon: "none" });
    }.bind(this));
  },

  addOne: function () {
    wx.showModal({
      title: "新增学生",
      editable: true,
      placeholderText: "姓名或 姓名,学号",
      success: function (res) {
        if (!res.confirm || !res.content.trim()) return;
        const parts = res.content.split(/[,，\t]/);
        api.addRosterStudent(this.data.classId, parts[0].trim(), (parts[1] || "").trim())
          .then(function () { wx.showToast({ title: "已新增", icon: "success" }); return this.loadRoster(); }.bind(this))
          .catch(function (error) { wx.showToast({ title: error.message || "新增失败", icon: "none" }); });
      }.bind(this)
    });
  },

  onBatchInput: function (event) {
    this.setData({ batchLines: event.detail.value || "" });
  },

  addBatch: function () {
    if (!this.data.batchLines.trim()) {
      wx.showToast({ title: "请输入名册内容", icon: "none" });
      return;
    }
    api.addRosterBatch(this.data.classId, this.data.batchLines).then(function (data) {
      this.setData({ batchLines: "" });
      wx.showToast({ title: "新增 " + data.created + " 人", icon: "success" });
      this.loadRoster();
    }.bind(this)).catch(function (error) {
      wx.showToast({ title: error.message || "批量新增失败", icon: "none" });
    });
  },

  unbind: function (event) {
    const id = Number(event.currentTarget.dataset.id);
    wx.showModal({
      title: "解除绑定",
      content: "只解除账号与名册关系，不删除作业和结果。确定继续？",
      success: function (res) {
        if (!res.confirm) return;
        api.unbindRosterStudent(this.data.classId, id).then(function () {
          wx.showToast({ title: "已解除", icon: "success" });
          this.loadRoster();
        }.bind(this)).catch(function (error) {
          wx.showToast({ title: error.message || "解除失败", icon: "none" });
        });
      }.bind(this)
    });
  },

  removeStudent: function (event) {
    const studentId = Number(event.currentTarget.dataset.studentId);
    if (!studentId || !this.data.isOwner) return;
    wx.showModal({
      title: "从班级移除学生",
      content: "只结束该学生在本班的名册关系；家庭绑定、其他班级和历史作业保留。",
      success: function (result) {
        if (!result.confirm) return;
        api.removeStudentFromClass(this.data.classId, studentId)
          .then(function () { wx.showToast({ title: "已从本班移除", icon: "success" }); this.loadRoster(); }.bind(this))
          .catch(function (error) { wx.showToast({ title: error.message || "移除失败", icon: "none" }); });
      }.bind(this)
    });
  }
});
