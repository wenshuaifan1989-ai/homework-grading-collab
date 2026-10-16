const api = require("../../../utils/api");
const auth = require("../../../utils/auth");

Page({
  data: {
    currentUser: null,
    name: "",
    schoolQuery: "",
    schoolStage: "",
    schoolOptions: [],
    selectedSchoolId: 0,
    selectedSchoolName: "",
    academicYear: "",
    semester: "",
    grade: "",
    saving: false
  },

  onShow: function () {
    auth.guardRole(this, "teacher");
  },

  onNameInput: function (event) {
    this.setData({ name: event.detail.value || "" });
  },

  onSchoolQueryInput: function (event) {
    this.setData({ schoolQuery: event.detail.value || "", selectedSchoolId: 0, selectedSchoolName: "" });
  },

  onSchoolStageInput: function (event) {
    this.setData({ schoolStage: event.detail.value || "", selectedSchoolId: 0, selectedSchoolName: "" });
  },

  findSchools: function () {
    api.searchSchools(this.data.schoolQuery.trim(), this.data.schoolStage.trim())
      .then(function (rows) {
        this.setData({ schoolOptions: rows || [] });
        if (!rows || !rows.length) wx.showToast({ title: "未找到学校，可登记待规范学校", icon: "none" });
      }.bind(this))
      .catch(function (error) { wx.showToast({ title: error.message || "学校搜索失败", icon: "none" }); });
  },

  selectSchool: function (event) {
    const school = this.data.schoolOptions.find(function (row) {
      return Number(row.id) === Number(event.currentTarget.dataset.id);
    });
    if (!school) return;
    this.setData({ selectedSchoolId: school.id, selectedSchoolName: school.official_name, schoolOptions: [] });
  },

  createCustomSchool: function () {
    const officialName = this.data.schoolQuery.trim();
    if (!officialName) {
      wx.showToast({ title: "请先输入学校名称", icon: "none" });
      return;
    }
    api.createCustomSchool({ official_name: officialName, stage: this.data.schoolStage.trim() || null })
      .then(function (school) {
        this.setData({
          selectedSchoolId: school.id,
          selectedSchoolName: school.official_name + (school.status === "pending_normalization" ? "（待规范）" : ""),
          schoolOptions: []
        });
      }.bind(this))
      .catch(function (error) { wx.showToast({ title: error.message || "学校登记失败", icon: "none" }); });
  },

  clearSchool: function () {
    this.setData({ selectedSchoolId: 0, selectedSchoolName: "" });
  },

  onAcademicYearInput: function (event) {
    this.setData({ academicYear: event.detail.value || "" });
  },

  onSemesterInput: function (event) {
    this.setData({ semester: event.detail.value || "" });
  },

  onGradeInput: function (event) {
    this.setData({ grade: event.detail.value || "" });
  },

  save: function () {
    const name = this.data.name.trim();
    if (!name) {
      wx.showToast({ title: "请填写班级名称", icon: "none" });
      return;
    }
    if (this.data.saving) return;
    this.setData({ saving: true });
    const payload = { name: name };
    if (this.data.selectedSchoolId) payload.school_id = this.data.selectedSchoolId;
    if (this.data.academicYear.trim()) payload.academic_year = this.data.academicYear.trim();
    if (this.data.semester.trim()) payload.semester = this.data.semester.trim();
    if (this.data.grade.trim()) payload.grade = this.data.grade.trim();
    api.createClass(payload).then(function (created) {
      wx.showModal({
        title: "班级创建成功",
        content: "邀请码：" + created.invite_code,
        showCancel: false,
        success: function () {
          wx.navigateBack({ delta: 1 });
        }
      });
    }.bind(this)).catch(function (error) {
      wx.showToast({ title: error.message || "创建失败", icon: "none" });
    }).then(function () {
      this.setData({ saving: false });
    }.bind(this));
  }
});
