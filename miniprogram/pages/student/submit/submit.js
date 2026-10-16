const api = require("../../../utils/api");
const auth = require("../../../utils/auth");

Page({
  data: {
    currentUser: null,
    assignmentId: 0,
    studentId: 0,
    studentName: "",
    images: [],
    assignmentTitle: "",
    subject: "math",
    grade: "grade7",
    subjects: [
      { code: "math", name: "数学" }, { code: "chinese", name: "语文" },
      { code: "english", name: "英语" }, { code: "physics", name: "物理" },
      { code: "chemistry", name: "化学" }, { code: "biology", name: "生物" },
      { code: "history", name: "历史" }, { code: "geography", name: "地理" }
    ],
    grades: [
      { code: "grade1", name: "一年级" }, { code: "grade2", name: "二年级" },
      { code: "grade3", name: "三年级" }, { code: "grade4", name: "四年级" },
      { code: "grade5", name: "五年级" }, { code: "grade6", name: "六年级" },
      { code: "grade7", name: "初一" }, { code: "grade8", name: "初二" },
      { code: "grade9", name: "初三" }
    ],
    subjectIndex: 0,
    gradeIndex: 6,
    submitting: false,
    variantMode: false,
    variantAvailable: true,
    variantMessage: ""
  },

  onLoad: function (options) {
    const studentId = Number(options.student_id || wx.getStorageSync("active_student_id") || 0);
    const rawAssignmentId = Number(options.id);
    const assignmentId = Number.isSafeInteger(rawAssignmentId) && rawAssignmentId > 0
      ? rawAssignmentId : 0;
    const independent = options.source === "independent";
    this.setData({
      assignmentId: assignmentId,
      studentId: studentId,
      independent: independent,
      assignmentTitle: independent ? "自主拍照批改" : ""
    });
    this.studentId = studentId;
  },

  onShow: function () {
    if (!auth.guardRole(this, "student")) return;
    this.loadTitle();
  },

  loadTitle: function () {
    if (this.data.independent || !this.data.assignmentId) return;
    api.studentAssignments(this.studentId).then(function (items) {
      const item = (items || []).find(function (row) {
        return Number(row.id) === this.data.assignmentId;
      }.bind(this));
      if (item) this.setData({
        assignmentTitle: item.title,
        subject: item.subject || "math",
        grade: item.grade || "grade7",
        studentName: item.student_name || "",
        variantMode: !!item.variant_mode,
        variantAvailable: item.variant_mode ? !!item.variant_available : true,
        variantMessage: item.variant_message || ""
      });
    }.bind(this)).catch(function () {});
  },

  chooseImages: function () {
    const remaining = 9 - this.data.images.length;
    if (remaining <= 0) {
      wx.showToast({ title: "最多选择 9 张", icon: "none" });
      return;
    }
    wx.chooseMedia({
      count: remaining,
      mediaType: ["image"],
      sourceType: ["album", "camera"],
      sizeType: ["compressed"],
      success: function (res) {
        const picked = (res.tempFiles || []).map(function (file, index) {
          return {
            path: file.tempFilePath,
            size: file.size || 0,
            key: Date.now() + "_" + index
          };
        });
        this.submissionKey = "";
        this.setData({ images: this.data.images.concat(picked).slice(0, 9) });
      }.bind(this),
      fail: function (error) {
        if (!error.errMsg || error.errMsg.indexOf("cancel") < 0) {
          wx.showToast({ title: "未能读取图片", icon: "none" });
        }
      }
    });
  },

  previewImage: function (event) {
    const path = event.currentTarget.dataset.path;
    wx.previewImage({
      current: path,
      urls: this.data.images.map(function (item) { return item.path; })
    });
  },

  removeImage: function (event) {
    const index = Number(event.currentTarget.dataset.index);
    const images = this.data.images.slice();
    images.splice(index, 1);
    this.submissionKey = "";
    this.setData({ images: images });
  },

  moveImage: function (event) {
    const index = Number(event.currentTarget.dataset.index);
    const direction = Number(event.currentTarget.dataset.direction);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= this.data.images.length) return;
    const images = this.data.images.slice();
    const item = images[index];
    images[index] = images[target];
    images[target] = item;
    this.submissionKey = "";
    this.setData({ images: images });
  },

  onSubjectChange: function (event) {
    const index = Number(event.detail.value) || 0;
    this.setData({ subjectIndex: index, subject: this.data.subjects[index].code });
  },

  onGradeChange: function (event) {
    const index = Number(event.detail.value) || 0;
    this.setData({ gradeIndex: index, grade: this.data.grades[index].code });
  },

  submit: function () {
    if (this.data.submitting) return;
    if (!this.data.independent && this.data.variantMode && !this.data.variantAvailable) {
      wx.showToast({ title: this.data.variantMessage || "老师尚未准备好本次练习", icon: "none" });
      return;
    }
    if (!this.data.images.length) {
      wx.showToast({ title: "请先拍摄或选择图片", icon: "none" });
      return;
    }
    if (!this.data.studentId) {
      wx.showToast({ title: "请先选择本次作业所属学生", icon: "none" });
      return;
    }
    this.setData({ submitting: true });
    if (!this.submissionKey) {
      this.submissionKey = "wx_" + Date.now().toString(36) + "_" +
        Math.random().toString(36).slice(2, 16);
    }
    wx.showLoading({ title: "正在提交整份作业", mask: true });

    // 1–9 images are encoded into one multipart body and sent with one POST.
    api.submitAssignment(
      this.data.images,
      this.data.assignmentId,
      this.data.subject,
      this.data.grade,
      this.data.studentId,
      this.submissionKey
    )
      .then(function (response) {
        if (!response || !response.task_id) throw new Error("服务未返回批改任务编号");
        this.submissionKey = "";
        wx.redirectTo({
          url: "/pages/student/result/result?task_id=" +
            encodeURIComponent(response.task_id)
        });
      }.bind(this))
      .catch(function (error) {
        wx.showToast({ title: error.message || "提交失败，请重试", icon: "none", duration: 3000 });
      })
      .then(function () {
        wx.hideLoading();
        this.setData({ submitting: false });
      }.bind(this));
  }
});
