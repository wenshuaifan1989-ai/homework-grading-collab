const api = require("../../../utils/api");
const auth = require("../../../utils/auth");

Page({
  data: {
    currentUser: null,
    classCount: 0
  },

  onShow: function () {
    if (!auth.guardRole(this, "teacher")) return;
    api.teacherClasses().then(function (classes) {
      this.setData({ classCount: (classes || []).length });
    }.bind(this)).catch(function () {});
  },

  openClasses: function () {
    wx.navigateTo({ url: "/pages/teacher/classes/classes" });
  },

  createClass: function () {
    wx.navigateTo({ url: "/pages/teacher/class-form/class-form" });
  },

  openFamilyHomework: function () {
    wx.navigateTo({ url: "/pages/student/homework/homework" });
  },

  openPaperReview: function () {
    wx.navigateTo({ url: "/pages/teacher/mistakes/mistakes" });
  },

  openLearning: function () {
    wx.navigateTo({ url: "/pages/teacher/learning/learning" });
  },

  logout: function () {
    auth.logout();
  }
});
