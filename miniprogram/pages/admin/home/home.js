const api = require("../../../utils/api");
const auth = require("../../../utils/auth");

Page({
  data: {
    currentUser: null,
    teachers: [],
    classes: [],
    loading: true
  },

  onShow: function () {
    if (auth.guardRole(this, "admin")) this.loadData();
  },

  loadData: function () {
    this.setData({ loading: true });
    Promise.all([api.adminTeachers(), api.adminClasses()]).then(function (values) {
      this.setData({ teachers: values[0] || [], classes: values[1] || [], loading: false });
    }.bind(this)).catch(function (error) {
      this.setData({ loading: false });
      wx.showToast({ title: error.message || "工作台加载失败", icon: "none" });
    }.bind(this));
  },

  createTeacher: function () {
    wx.showModal({ title: "创建教师", editable: true, placeholderText: "教师手机号", success: function (phoneRes) {
      if (!phoneRes.confirm || !phoneRes.content.trim()) return;
      wx.showModal({ title: "设置初始密码", editable: true, placeholderText: "至少 8 位密码", success: function (passwordRes) {
        if (!passwordRes.confirm || !passwordRes.content) return;
        wx.showModal({ title: "教师姓名", editable: true, placeholderText: "真实姓名", success: function (nameRes) {
          if (!nameRes.confirm || !nameRes.content.trim()) return;
          api.adminCreateTeacher(phoneRes.content.trim(), passwordRes.content, nameRes.content.trim())
            .then(function () { wx.showToast({ title: "教师已创建", icon: "success" }); this.loadData(); }.bind(this))
            .catch(function (error) { wx.showToast({ title: error.message || "创建失败", icon: "none" }); });
        }.bind(this) });
      }.bind(this) });
    }.bind(this) });
  },

  toggleTeacher: function (event) {
    const teacherId = Number(event.currentTarget.dataset.id);
    const active = event.currentTarget.dataset.active;
    const nextStatus = !(active === true || active === "true" || active === 1 || active === "1");
    api.adminTeacherStatus(teacherId, nextStatus).then(function () {
      this.loadData();
    }.bind(this)).catch(function (error) {
      wx.showToast({ title: error.message || "状态更新失败", icon: "none" });
    });
  },

  openRoster: function (event) {
    wx.navigateTo({ url: "/pages/teacher/roster/roster?id=" + event.currentTarget.dataset.id });
  },

  openFamilyHomework: function () {
    wx.navigateTo({ url: "/pages/student/homework/homework" });
  },

  logout: function () {
    auth.logout();
  }
});
