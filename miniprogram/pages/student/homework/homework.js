const api = require("../../../utils/api");
const auth = require("../../../utils/auth");
const display = require("../../../utils/display");

Page({
  data: {
    currentUser: null,
    students: [],
    selectedStudentId: 0,
    selectedStudentName: "",
    assignments: [],
    visibleAssignments: [],
    independentTasks: [],
    activeTab: "pending",
    loading: false
  },

  onShow: function () {
    if (auth.guardRole(this, "student")) {
      this.loadStudents().then(function () {
        if (!this.data.students.length) {
          wx.reLaunch({ url: "/pages/student/bind/bind" });
          return;
        }
        this.loadIndependentHistory();
        if (!this.data.selectedStudentId) return;
        this.loadAssignments();
      }.bind(this));
    }
  },

  onPullDownRefresh: function () {
    this.loadAssignments().then(function () { wx.stopPullDownRefresh(); });
  },

  loadAssignments: function () {
    if (!this.data.selectedStudentId) return Promise.resolve();
    this.setData({ loading: true });
    return api.studentAssignments(this.data.selectedStudentId).then(function (items) {
      const assignments = (items || []).map(function (item) {
        item.dueLabel = display.dateLabel(item.due_at);
        item.statusLabel = item.submitted
          ? display.statusLabel(item.task_status)
          : "待完成";
        return item;
      });
      this.setData({ assignments: assignments });
      this.applyTab(this.data.activeTab);
    }.bind(this)).catch(function (error) {
      wx.showToast({ title: error.message || "作业加载失败", icon: "none" });
    }).then(function () {
      this.setData({ loading: false });
    }.bind(this));
  },

  loadIndependentHistory: function () {
    return api.homeworkHistory().then(function (response) {
      const rows = response && Array.isArray(response.items) ? response.items : [];
      const labels = { math: "数学", chinese: "语文", english: "英语", physics: "物理", chemistry: "化学", biology: "生物" };
      const tasks = rows.filter(function (item) { return item.assignment_id == null; })
        .map(function (item) {
          item.subjectLabel = labels[item.subject] || item.subject || "自主练习";
          item.statusLabel = display.statusLabel(item.status);
          item.createdLabel = display.dateLabel(item.created_at);
          return item;
        });
      this.setData({ independentTasks: tasks });
    }.bind(this)).catch(function (error) {
      wx.showToast({ title: error.message || "自主练习记录加载失败", icon: "none" });
    });
  },

  loadStudents: function () {
    return api.myStudents().then(function (items) {
      const students = (items || []).filter(function (item) { return item.status === "active"; });
      const stored = Number(wx.getStorageSync("active_student_id") || 0);
      const selected = students.some(function (item) { return item.student_id === stored; })
        ? stored : (students.length === 1 ? students[0].student_id : 0);
      const selectedStudent = students.find(function (item) { return item.student_id === selected; });
      this.setData({
        students: students,
        selectedStudentId: selected,
        selectedStudentName: selectedStudent ? selectedStudent.name : ""
      });
      if (selected) wx.setStorageSync("active_student_id", selected);
      if (students.length > 1 && !selected) {
        this.setData({ assignments: [], visibleAssignments: [] });
      }
    }.bind(this)).catch(function (error) {
      wx.showToast({ title: error.message || "学生身份加载失败", icon: "none" });
    });
  },

  selectStudent: function (event) {
    const id = Number(event.currentTarget.dataset.id);
    if (!id || id === this.data.selectedStudentId) return;
    const student = this.data.students.find(function (item) { return item.student_id === id; });
    this.setData({
      selectedStudentId: id,
      selectedStudentName: student ? student.name : "",
      activeTab: "pending"
    });
    wx.setStorageSync("active_student_id", id);
    this.loadAssignments();
  },

  openRelations: function () {
    wx.navigateTo({ url: "/pages/student/bind/bind" });
  },

  openMistakes: function () {
    wx.navigateTo({ url: "/pages/student/mistakes/mistakes" });
  },

  openIndependentPractice: function () {
    if (!this.data.selectedStudentId) {
      wx.showToast({ title: "请先绑定学生身份", icon: "none" });
      return;
    }
    wx.navigateTo({ url: "/pages/student/submit/submit?source=independent&student_id=" + encodeURIComponent(this.data.selectedStudentId) });
  },

  openIndependentResult: function (event) {
    const taskId = event.currentTarget.dataset.taskId;
    if (!taskId) return;
    wx.navigateTo({ url: "/pages/student/result/result?task_id=" + encodeURIComponent(taskId) });
  },

  selectTab: function (event) {
    this.applyTab(event.currentTarget.dataset.tab);
  },

  applyTab: function (tab) {
    const list = this.data.assignments.filter(function (item) {
      const complete = item.submitted && item.task_status !== "FAILED";
      return tab === "completed" ? complete : !complete;
    });
    this.setData({ activeTab: tab, visibleAssignments: list });
  },

  openAssignment: function (event) {
    const id = event.currentTarget.dataset.id;
    wx.navigateTo({
      url: "/pages/student/detail/detail?id=" + id +
        "&student_id=" + encodeURIComponent(this.data.selectedStudentId)
    });
  },

  logout: function () {
    auth.logout();
  }
});
