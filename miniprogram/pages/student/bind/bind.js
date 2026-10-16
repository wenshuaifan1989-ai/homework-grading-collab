const api = require("../../../utils/api");
const auth = require("../../../utils/auth");

const RELATIONSHIPS = [
  { value: "father", label: "父亲" },
  { value: "mother", label: "母亲" },
  { value: "paternal_grandfather", label: "祖父" },
  { value: "paternal_grandmother", label: "祖母" },
  { value: "maternal_grandfather", label: "外祖父" },
  { value: "maternal_grandmother", label: "外祖母" },
  { value: "guardian", label: "监护人" },
  { value: "other", label: "其他" }
];

Page({
  data: {
    currentUser: null,
    students: [],
    selectedStudentId: 0,
    classCode: "",
    studentName: "",
    candidates: [],
    selectedRosterId: 0,
    familyCode: "",
    relationshipIndex: 0,
    relationshipLabels: RELATIONSHIPS.map(function (item) { return item.label; }),
    loading: false,
    binding: false
  },

  onShow: function () {
    const session = auth.getSession();
    if (!session.token || !session.user) {
      wx.reLaunch({ url: "/pages/login/login" });
      return;
    }
    this.setData({ currentUser: session.user });
    this.loadStudents();
  },

  loadStudents: function () {
    return api.myStudents().then(function (students) {
      const active = (students || []).filter(function (item) { return item.status === "active"; });
      const saved = Number(wx.getStorageSync("active_student_id") || 0);
      const selected = active.some(function (item) { return item.student_id === saved; })
        ? saved : (active.length === 1 ? active[0].student_id : 0);
      this.setData({ students: active, selectedStudentId: selected });
      if (selected) wx.setStorageSync("active_student_id", selected);
      const user = Object.assign({}, this.data.currentUser, {
        bind_status: active.length ? "bound" : "unbound",
        student_id: selected || null
      });
      this.setData({ currentUser: user });
      getApp().saveSession(wx.getStorageSync("access_token"), user);
    }.bind(this)).catch(function (error) {
      wx.showToast({ title: error.message || "身份列表加载失败", icon: "none" });
    });
  },

  selectStudent: function (event) {
    const id = Number(event.currentTarget.dataset.id);
    this.setData({ selectedStudentId: id, selectedRosterId: 0 });
    wx.setStorageSync("active_student_id", id);
  },

  onClassCodeInput: function (event) {
    this.setData({ classCode: (event.detail.value || "").trim() });
  },

  onStudentNameInput: function (event) {
    this.setData({ studentName: event.detail.value || "", candidates: [], selectedRosterId: 0 });
  },

  selectCandidate: function (event) {
    this.setData({ selectedRosterId: Number(event.currentTarget.dataset.id) });
  },

  joinClass: function () {
    if (!this.data.classCode || !this.data.studentName.trim()) {
      wx.showToast({ title: "请输入班级邀请码和学生姓名", icon: "none" });
      return;
    }
    if (this.data.students.length > 1 && !this.data.selectedStudentId) {
      wx.showToast({ title: "请先选择本次加入班级的学生身份", icon: "none" });
      return;
    }
    if (this.data.candidates.length && !this.data.selectedRosterId) {
      wx.showToast({ title: "同名学生，请核对后选择名册记录", icon: "none" });
      return;
    }
    if (this.data.binding) return;
    this.setData({ binding: true });
    const payload = { student_name: this.data.studentName.trim() };
    if (this.data.selectedStudentId) payload.student_id = this.data.selectedStudentId;
    if (this.data.selectedRosterId) payload.roster_id = this.data.selectedRosterId;
    api.claimContract(this.data.classCode, payload)
      .then(function (data) {
        if (data && data.requires_disambiguation) {
          this.setData({ candidates: data.candidates || [], selectedRosterId: 0, binding: false });
          return;
        }
        if (!data || !data.joined) throw new Error("服务未确认班级关系");
        wx.setStorageSync("active_student_id", data.student_id);
        const user = Object.assign({}, this.data.currentUser, {
          bind_status: "bound",
          student_id: data.student_id,
          student_name: data.student_name,
          bound_class_id: data.class_id,
          bound_class_name: data.class_name
        });
        getApp().saveSession(wx.getStorageSync("access_token"), user);
        wx.showToast({ title: "已加入班级", icon: "success" });
        setTimeout(function () { wx.reLaunch({ url: auth.homeForRole("student") }); }, 350);
      }.bind(this))
      .catch(function (error) {
        wx.showToast({ title: error.message || "加入失败，请核对邀请码和姓名", icon: "none" });
      })
      .then(function () { this.setData({ binding: false }); }.bind(this));
  },

  onFamilyCodeInput: function (event) {
    this.setData({ familyCode: (event.detail.value || "").trim() });
  },

  onRelationshipChange: function (event) {
    this.setData({ relationshipIndex: Number(event.detail.value) || 0 });
  },

  bindFamily: function () {
    if (!this.data.familyCode) {
      wx.showToast({ title: "请输入家庭关系码", icon: "none" });
      return;
    }
    if (this.data.binding) return;
    this.setData({ binding: true });
    const relationship = RELATIONSHIPS[this.data.relationshipIndex];
    api.claimContract(this.data.familyCode, {
      relationship_type: relationship.value
    }).then(function (data) {
      if (!data || !data.bound) throw new Error("服务未确认家庭关系");
      wx.setStorageSync("active_student_id", data.student_id);
      wx.showToast({ title: data.already_bound ? "该学生已在身份列表中" : "家庭关系已建立", icon: "success" });
      this.setData({ familyCode: "" });
      return this.loadStudents();
    }.bind(this)).catch(function (error) {
      wx.showToast({ title: error.message || "关系码无效或已使用", icon: "none" });
    }).then(function () { this.setData({ binding: false }); }.bind(this));
  },

  createFamilyInvite: function (event) {
    const studentId = Number(event.currentTarget.dataset.id);
    api.createFamilyContract(studentId).then(function (contract) {
      wx.showModal({
        title: "家庭邀请已生成",
        content: "请将关系码提供给家庭成员：\n" + contract.code,
        confirmText: "复制关系码",
        success: function (result) {
          if (result.confirm) wx.setClipboardData({ data: contract.code });
        }
      });
    }).catch(function (error) {
      wx.showToast({ title: error.message || "生成邀请失败", icon: "none" });
    });
  },

  removeFamilyBinding: function (event) {
    const studentId = Number(event.currentTarget.dataset.id);
    wx.showModal({
      title: "解除家庭关系",
      content: "如果这是该学生最后一个家庭关系，将提交 owner / 平台管理员审核，不会直接删除学生或历史作业。",
      success: function (result) {
        if (!result.confirm) return;
        api.removeFamilyBinding(studentId, this.data.currentUser.id)
          .then(function (data) {
            wx.showToast({
              title: data.requires_review ? "已提交审核" : "关系已解除",
              icon: "success"
            });
            return this.loadStudents();
          }.bind(this))
          .catch(function (error) { wx.showToast({ title: error.message || "解除失败", icon: "none" }); });
      }.bind(this)
    });
  },

  requestLeaveClass: function (event) {
    const studentId = Number(event.currentTarget.dataset.studentId);
    const classId = Number(event.currentTarget.dataset.classId);
    wx.showModal({
      title: "申请退出班级",
      content: "申请后由班级 owner 确认；其他班级、家庭关系和历史作业不受影响。",
      success: function (result) {
        if (!result.confirm) return;
        api.requestStudentLeave(studentId, classId)
          .then(function () {
            wx.showToast({ title: "已提交退出申请", icon: "success" });
            this.loadStudents();
          }.bind(this))
          .catch(function (error) { wx.showToast({ title: error.message || "申请失败", icon: "none" }); });
      }.bind(this)
    });
  },

  backToHome: function () {
    if (this.data.students.length) wx.navigateBack({ delta: 1 });
    else wx.reLaunch({ url: auth.homeForRole("student") });
  },

  logout: function () {
    auth.logout();
  }
});
