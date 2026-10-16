const api = require("../../../utils/api");
const auth = require("../../../utils/auth");

const LEVELS = [
  { code: "L1", label: "基础巩固" },
  { code: "L2", label: "稳定提升" },
  { code: "L3", label: "拓展挑战" }
];
const TIER_LEVELS = [{ code: "", label: "待分层" }].concat(LEVELS);

Page({
  data: {
    currentUser: null,
    classes: [],
    classIndex: 0,
    classId: 0,
    subjects: [
      { value: "math", label: "数学" }, { value: "chinese", label: "语文" },
      { value: "english", label: "英语" }, { value: "physics", label: "物理" },
      { value: "chemistry", label: "化学" }, { value: "biology", label: "生物" },
      { value: "history", label: "历史" }, { value: "geography", label: "地理" }
    ],
    subjectIndex: 0,
    tierRows: [],
    levels: LEVELS,
    tierLevels: TIER_LEVELS,
    assignments: [],
    assignmentIndex: 0,
    assignmentId: 0,
    variantDrafts: LEVELS.map(function (level) {
      return { code: level.code, label: level.label, questions: "", answers: "", version: 0 };
    }),
    fallbackEnabled: false,
    fallbackIndex: 1,
    loading: false,
    saving: false
  },

  onShow: function () {
    if (auth.guardRole(this, "teacher")) this.loadWorkspace();
  },

  onPullDownRefresh: function () {
    this.loadWorkspace().then(function () { wx.stopPullDownRefresh(); });
  },

  loadWorkspace: function () {
    this.setData({ loading: true });
    api.teacherClasses().then(function (classes) {
      const list = classes || [];
      const stored = wx.getStorageSync("selected_class") || {};
      const match = list.findIndex(function (item) { return Number(item.id) === Number(stored.id); });
      const classIndex = match >= 0 ? match : 0;
      this.setData({ classes: list, classIndex: classIndex, classId: list[classIndex] ? list[classIndex].id : 0 });
      if (!list.length) {
        this.setData({ tierRows: [], assignments: [], assignmentId: 0, loading: false });
        return;
      }
      return this.loadClassData();
    }.bind(this)).catch(function (error) {
      this.setData({ loading: false });
      wx.showToast({ title: error.message || "读取教师班级失败", icon: "none" });
    }.bind(this));
  },

  loadClassData: function () {
    if (!this.data.classId) return Promise.resolve();
    this.setData({ loading: true });
    const subject = this.data.subjects[this.data.subjectIndex].value;
    return Promise.all([
      api.learningTiers(this.data.classId, subject),
      api.teacherAssignments(this.data.classId)
    ]).then(function (results) {
      const tierData = results[0] || {};
      const assignments = results[1] || [];
      const oldAssignment = Number(this.data.assignmentId);
      const foundIndex = assignments.findIndex(function (item) { return Number(item.id) === oldAssignment; });
      const assignmentIndex = foundIndex >= 0 ? foundIndex : 0;
      this.setData({
        tierRows: this.decorateTierRows(tierData.students || []),
        assignments: assignments,
        assignmentIndex: assignmentIndex,
        assignmentId: assignments[assignmentIndex] ? assignments[assignmentIndex].id : 0,
        loading: false
      });
      if (assignments[assignmentIndex]) return this.loadVariants(assignments[assignmentIndex].id);
      this.setData({ variantDrafts: this.emptyDrafts(), fallbackEnabled: false, loading: false });
    }.bind(this)).catch(function (error) {
      this.setData({ loading: false });
      wx.showToast({ title: error.message || "读取分层或作业失败", icon: "none" });
    }.bind(this));
  },

  decorateTierRows: function (rows) {
    return rows.map(function (row) {
      const levelIndex = TIER_LEVELS.findIndex(function (item) { return item.code === row.level; });
      return Object.assign({}, row, { selectedLevel: row.level || "", levelIndex: levelIndex >= 0 ? levelIndex : 0 });
    });
  },

  emptyDrafts: function () {
    return LEVELS.map(function (level) {
      return { code: level.code, label: level.label, questions: "", answers: "", version: 0 };
    });
  },

  onClassChange: function (event) {
    const index = Number(event.detail.value) || 0;
    const classroom = this.data.classes[index];
    if (!classroom) return;
    wx.setStorageSync("selected_class", classroom);
    this.setData({ classIndex: index, classId: classroom.id, assignmentId: 0 });
    this.loadClassData();
  },

  onSubjectChange: function (event) {
    const index = Number(event.detail.value) || 0;
    this.setData({ subjectIndex: index });
    this.loadClassData();
  },

  onTierChange: function (event) {
    const index = Number(event.currentTarget.dataset.index);
    const levelIndex = Number(event.detail.value) || 0;
    const row = this.data.tierRows[index];
    if (!row) return;
    this.setData({
      ["tierRows[" + index + "].levelIndex"]: levelIndex,
      ["tierRows[" + index + "].selectedLevel"]: TIER_LEVELS[levelIndex].code
    });
  },

  saveTiers: function () {
    const entries = this.data.tierRows.filter(function (row) {
      return row.student_id && row.selectedLevel;
    }).map(function (row) {
      return { student_id: row.student_id, level: row.selectedLevel };
    });
    if (!entries.length) {
      wx.showToast({ title: "请先为已绑定学生选择层级", icon: "none" });
      return;
    }
    this.setData({ saving: true });
    api.saveLearningTiers(this.data.classId, this.data.subjects[this.data.subjectIndex].value, entries)
      .then(function (result) {
        this.setData({ tierRows: this.decorateTierRows(result.students || []) });
        wx.showToast({ title: "学科分层已保存", icon: "success" });
      }.bind(this)).catch(function (error) {
        wx.showToast({ title: error.message || "保存分层失败", icon: "none" });
      }).then(function () { this.setData({ saving: false }); }.bind(this));
  },

  onAssignmentChange: function (event) {
    const index = Number(event.detail.value) || 0;
    const assignment = this.data.assignments[index];
    if (!assignment) return;
    this.setData({ assignmentIndex: index, assignmentId: assignment.id });
    this.loadVariants(assignment.id);
  },

  loadVariants: function (assignmentId) {
    if (!assignmentId) return Promise.resolve();
    return api.learningVariants(assignmentId).then(function (result) {
      const drafts = this.emptyDrafts();
      (result.variants || []).forEach(function (variant) {
        const index = drafts.findIndex(function (draft) { return draft.code === variant.level; });
        if (index < 0) return;
        drafts[index].version = variant.version;
        drafts[index].questions = (variant.questions || []).map(function (question) { return question.question_text; }).join("\n");
        drafts[index].answers = (variant.questions || []).map(function (question) { return question.correct_answer || ""; }).join("\n");
      });
      const fallbackIndex = Math.max(0, LEVELS.findIndex(function (level) { return level.code === result.uniform_fallback_level; }));
      this.setData({
        variantDrafts: drafts,
        fallbackEnabled: !!result.allow_uniform_fallback,
        fallbackIndex: fallbackIndex
      });
    }.bind(this)).catch(function (error) {
      wx.showToast({ title: error.message || "读取三层作业失败", icon: "none" });
    });
  },

  onVariantInput: function (event) {
    const index = Number(event.currentTarget.dataset.index);
    const field = event.currentTarget.dataset.field;
    if (index < 0 || index > 2 || (field !== "questions" && field !== "answers")) return;
    this.setData({ ["variantDrafts[" + index + "]." + field]: event.detail.value || "" });
  },

  toggleFallback: function (event) {
    const selected = event.detail.value || [];
    this.setData({ fallbackEnabled: selected.indexOf("allow") >= 0 });
  },

  onFallbackChange: function (event) {
    this.setData({ fallbackIndex: Number(event.detail.value) || 0 });
  },

  saveVariants: function () {
    if (!this.data.assignmentId) {
      wx.showToast({ title: "当前班级还没有已发布作业", icon: "none" });
      return;
    }
    const variants = this.data.variantDrafts.map(function (draft) {
      const questions = draft.questions.split(/\r?\n/).map(function (line) { return line.trim(); }).filter(Boolean);
      const answers = draft.answers.split(/\r?\n/);
      return {
        level: draft.code,
        questions: questions.map(function (question, index) {
          return { question_text: question, correct_answer: (answers[index] || "").trim() || null, max_score: 10 };
        })
      };
    });
    const empty = variants.find(function (variant) { return !variant.questions.length; });
    if (empty) {
      wx.showToast({ title: empty.level + " 还没有题目，请补齐三个版本", icon: "none" });
      return;
    }
    this.setData({ saving: true });
    api.saveLearningVariants(this.data.assignmentId, {
      allow_uniform_fallback: this.data.fallbackEnabled,
      uniform_fallback_level: this.data.fallbackEnabled ? LEVELS[this.data.fallbackIndex].code : null,
      variants: variants
    }).then(function (result) {
      wx.showToast({ title: "三个版本已保存", icon: "success" });
      return this.loadVariants(this.data.assignmentId);
    }.bind(this)).catch(function (error) {
      wx.showToast({ title: error.message || "保存三层作业失败", icon: "none" });
    }).then(function () { this.setData({ saving: false }); }.bind(this));
  },

  openPrintable: function (event) {
    const level = event.currentTarget.dataset.level;
    api.downloadLearningVariant(this.data.assignmentId, level).then(function (filePath) {
      wx.openDocument({
        filePath: filePath,
        showMenu: true,
        fail: function () { wx.showToast({ title: "PDF 打开失败，请在教师Web下载打印", icon: "none" }); }
      });
    }).catch(function (error) {
      wx.showToast({ title: error.message || "下载题目PDF失败", icon: "none" });
    });
  }
});
