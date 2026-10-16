const api = require("../../../utils/api");
const auth = require("../../../utils/auth");

function pad(number) {
  return number < 10 ? "0" + number : String(number);
}

function localDate(value) {
  const date = value ? new Date(value + "T00:00:00") : new Date();
  return date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate());
}

function addDays(value, amount) {
  const date = new Date(value + "T00:00:00");
  date.setDate(date.getDate() + amount);
  return localDate(date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate()));
}

function monthOf(value) {
  return value.slice(0, 7);
}

Page({
  data: {
    classId: 0,
    className: "",
    date: localDate(),
    month: monthOf(localDate()),
    calendarDates: [],
    assignments: [],
    selectedAssignmentId: 0,
    classStats: null,
    questionStats: [],
    students: [],
    filter: "all",
    loading: true
  },

  onLoad: function (options) {
    const classroom = wx.getStorageSync("selected_class") || {};
    this.classId = Number(options.id);
    this.setData({ classId: this.classId, className: classroom.name || "" });
  },

  onShow: function () {
    if (auth.guardRole(this, "teacher")) this.loadAll();
  },

  onPullDownRefresh: function () {
    this.loadAll().then(function () { wx.stopPullDownRefresh(); });
  },

  loadAll: function () {
    if (!this.classId) return Promise.resolve();
    this.setData({ loading: true });
    const date = this.data.date;
    return Promise.all([
      api.classCalendar(this.classId, monthOf(date)),
      api.classDailyDashboard(this.classId, date, this.data.selectedAssignmentId || null)
    ]).then(function (values) {
      const calendar = values[0] || {};
      const dashboard = values[1] || {};
      this.setData({
        month: calendar.month || monthOf(date),
        calendarDates: calendar.dates || [],
        assignments: dashboard.assignments || [],
        selectedAssignmentId: dashboard.selected_assignment_id || 0,
        classStats: dashboard.class || null,
        questionStats: dashboard.question_stats || [],
        students: dashboard.students || [],
        loading: false
      });
    }.bind(this)).catch(function (error) {
      this.setData({ loading: false });
      wx.showToast({ title: error.message || "仪表盘加载失败", icon: "none" });
    }.bind(this));
  },

  chooseDate: function (event) {
    const value = event.detail.value;
    this.setData({ date: value, month: monthOf(value), selectedAssignmentId: 0 });
    this.loadAll();
  },

  moveDate: function (event) {
    const amount = Number(event.currentTarget.dataset.amount);
    const value = addDays(this.data.date, amount);
    this.setData({ date: value, month: monthOf(value), selectedAssignmentId: 0 });
    this.loadAll();
  },

  selectAssignment: function (event) {
    const id = Number(event.currentTarget.dataset.id);
    this.setData({ selectedAssignmentId: id, loading: true });
    api.classDailyDashboard(this.classId, this.data.date, id).then(function (dashboard) {
      this.setData({
        assignments: dashboard.assignments || [],
        selectedAssignmentId: dashboard.selected_assignment_id || id,
        classStats: dashboard.class || null,
        questionStats: dashboard.question_stats || [],
        students: dashboard.students || [],
        loading: false,
        filter: "all"
      });
    }.bind(this)).catch(function (error) {
      this.setData({ loading: false });
      wx.showToast({ title: error.message || "作业切换失败", icon: "none" });
    }.bind(this));
  },

  setFilter: function (event) {
    this.setData({ filter: event.currentTarget.dataset.filter });
  },

  filteredStudents: function () {
    const filter = this.data.filter;
    if (filter === "all") return this.data.students;
    return this.data.students.filter(function (item) {
      return filter === "unbound" ? item.bind_status === "unbound" : item.submission_status === filter;
    });
  },

  openQuestion: function (event) {
    if (!this.data.selectedAssignmentId) return;
    const key = event.currentTarget.dataset.key;
    wx.navigateTo({
      url: "/pages/teacher/question-students/question-students?assignment_id=" +
        this.data.selectedAssignmentId + "&question_key=" + encodeURIComponent(key)
    });
  },

  openStudent: function (event) {
    const studentId = event.currentTarget.dataset.student;
    if (!studentId || !this.data.selectedAssignmentId) return;
    wx.navigateTo({
      url: "/pages/teacher/result/result?assignment_id=" +
        this.data.selectedAssignmentId + "&student_id=" + studentId
    });
  },

  openRoster: function () {
    wx.navigateTo({ url: "/pages/teacher/roster/roster?id=" + this.classId });
  },

  openAssignments: function () {
    wx.navigateTo({ url: "/pages/teacher/assignments/assignments?id=" + this.classId });
  }
});
