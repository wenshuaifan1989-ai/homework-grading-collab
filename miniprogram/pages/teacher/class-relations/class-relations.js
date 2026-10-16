const api = require("../../../utils/api");
const auth = require("../../../utils/auth");

Page({
  data: {
    currentUser: null,
    classId: 0,
    className: "班级",
    teachers: [],
    pendingLeaves: [],
    pendingFamilyBindings: [],
    isOwner: false,
    loading: true
  },

  onLoad: function (options) {
    const classroom = wx.getStorageSync("selected_class") || {};
    this.setData({
      classId: Number(options.id || 0),
      className: classroom.name || "班级"
    });
  },

  onShow: function () {
    const session = auth.getSession();
    if (!session.token || !session.user || session.user.role !== "teacher") {
      wx.reLaunch({ url: "/pages/login/login" });
      return;
    }
    this.setData({ currentUser: session.user });
    this.loadTeachers();
  },

  loadTeachers: function () {
    this.setData({ loading: true });
    return api.classTeachers(this.data.classId).then(function (teachers) {
      const rows = (teachers || []).map(function (row) {
        row.subjectLabel = row.subject_codes && row.subject_codes.length
          ? row.subject_codes.join("、") : "未限定学科";
        return row;
      });
      const mine = rows.find(function (row) { return Number(row.user_id) === Number(this.data.currentUser.id); }.bind(this));
      const isOwner = !!mine && mine.role === "owner";
      this.setData({ teachers: rows, isOwner: isOwner, loading: false });
      if (!isOwner) {
        this.setData({ pendingLeaves: [], pendingFamilyBindings: [] });
        return;
      }
      return api.classRelationRequests(this.data.classId).then(function (requests) {
        this.setData({
          pendingLeaves: requests.student_leave || [],
          pendingFamilyBindings: requests.family_binding || []
        });
      }.bind(this));
    }.bind(this)).catch(function (error) {
      this.setData({ loading: false });
      wx.showToast({ title: error.message || "班级关系加载失败", icon: "none" });
    }.bind(this));
  },

  inviteTeacher: function () {
    api.createClassContract(this.data.classId, "TEACHER_CLASS_JOIN", 1).then(function (contract) {
      wx.showModal({
        title: "教师邀请已生成",
        content: "一次性邀请码（7 天有效）：\n" + contract.code,
        confirmText: "复制",
        success: function (result) {
          if (result.confirm) wx.setClipboardData({ data: contract.code });
        }
      });
    }).catch(function (error) { wx.showToast({ title: error.message || "生成邀请失败", icon: "none" }); });
  },

  removeTeacher: function (event) {
    const teacherId = Number(event.currentTarget.dataset.id);
    wx.showModal({
      title: "移除教师",
      content: "只撤销该教师的本班权限，不删除账号或历史作业。",
      success: function (result) {
        if (!result.confirm) return;
        api.removeClassTeacher(this.data.classId, teacherId)
          .then(function () { wx.showToast({ title: "教师已移除", icon: "success" }); this.loadTeachers(); }.bind(this))
          .catch(function (error) { wx.showToast({ title: error.message || "移除失败", icon: "none" }); });
      }.bind(this)
    });
  },

  transferOwner: function () {
    const candidates = this.data.teachers.filter(function (row) { return row.role !== "owner"; });
    if (!candidates.length) {
      wx.showToast({ title: "需要先邀请另一位教师", icon: "none" });
      return;
    }
    wx.showActionSheet({
      itemList: candidates.map(function (row) { return row.name; }),
      success: function (result) {
        const target = candidates[result.tapIndex];
        if (!target) return;
        wx.showModal({
          title: "转移班级 owner",
          content: "转移后你将成为普通教师，确认把 owner 转给“" + target.name + "”吗？",
          success: function (confirm) {
            if (!confirm.confirm) return;
            api.transferClassOwner(this.data.classId, target.user_id)
              .then(function () { wx.showToast({ title: "owner 已转移", icon: "success" }); this.loadTeachers(); }.bind(this))
              .catch(function (error) { wx.showToast({ title: error.message || "转移失败", icon: "none" }); });
          }.bind(this)
        });
      }.bind(this)
    });
  },

  resetStudentInvite: function () {
    wx.showModal({
      title: "重置学生加入码",
      content: "旧码立即失效，但已加入的学生关系不受影响。",
      success: function (result) {
        if (!result.confirm) return;
        api.createClassContract(this.data.classId, "STUDENT_CLASS_JOIN")
          .then(function (contract) {
            const classroom = wx.getStorageSync("selected_class") || {};
            classroom.invite_code = contract.code;
            wx.setStorageSync("selected_class", classroom);
            wx.showModal({
              title: "学生加入码已重置",
              content: contract.code,
              confirmText: "复制",
              success: function (copy) { if (copy.confirm) wx.setClipboardData({ data: contract.code }); }
            });
          })
          .catch(function (error) { wx.showToast({ title: error.message || "重置失败", icon: "none" }); });
      }.bind(this)
    });
  },

  leaveClass: function () {
    wx.showModal({
      title: "退出教师关系",
      content: "你将不再访问本班；owner 需先转移权限或结束班级。",
      success: function (result) {
        if (!result.confirm) return;
        api.leaveClassAsTeacher(this.data.classId)
          .then(function () { wx.navigateBack({ delta: 1 }); })
          .catch(function (error) { wx.showToast({ title: error.message || "无法退出", icon: "none" }); });
      }.bind(this)
    });
  },

  changeClassStatus: function (event) {
    const status = event.currentTarget.dataset.status;
    const label = status === "archived" ? "归档" : "终止";
    wx.showModal({
      title: label + "班级",
      content: status === "archived"
        ? "用于正常毕业或结束；历史记录保留。"
        : "用于错建或终止；采用软状态，数据不会删除。",
      success: function (result) {
        if (!result.confirm) return;
        api.updateClassStatus(this.data.classId, status)
          .then(function () { wx.showToast({ title: "班级已" + label, icon: "success" }); wx.navigateBack({ delta: 1 }); })
          .catch(function (error) { wx.showToast({ title: error.message || "更新失败", icon: "none" }); });
      }.bind(this)
    });
  },

  reviewStudentLeave: function (event) {
    const studentId = Number(event.currentTarget.dataset.studentId);
    const approve = event.currentTarget.dataset.approve === "true";
    api.reviewStudentLeave(this.data.classId, studentId, approve)
      .then(function () { wx.showToast({ title: approve ? "已批准退出" : "已保留在班级", icon: "success" }); this.loadTeachers(); }.bind(this))
      .catch(function (error) { wx.showToast({ title: error.message || "审核失败", icon: "none" }); });
  },

  reviewFamilyBinding: function (event) {
    const studentId = Number(event.currentTarget.dataset.studentId);
    const userId = Number(event.currentTarget.dataset.userId);
    const approve = event.currentTarget.dataset.approve === "true";
    api.reviewFamilyBinding(studentId, userId, approve)
      .then(function () { wx.showToast({ title: approve ? "关系已解除" : "已保留关系", icon: "success" }); this.loadTeachers(); }.bind(this))
      .catch(function (error) { wx.showToast({ title: error.message || "审核失败", icon: "none" }); });
  }
});
