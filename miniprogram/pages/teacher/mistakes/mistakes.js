const api = require("../../../utils/api");
const auth = require("../../../utils/auth");

Page({
  data: {
    currentUser: null,
    classes: [],
    assignments: [],
    submissions: [],
    eligibleSubmissions: [],
    sources: [],
    gradingOptions: [],
    mistakes: [],
    classIndex: 0,
    assignmentIndex: 0,
    submissionIndex: 0,
    gradingIndex: 0,
    classId: 0,
    assignmentId: 0,
    taskId: "",
    selectedSourceId: 0,
    selectedSource: null,
    gradingResultId: 0,
    questionNo: "",
    questionText: "",
    questionType: "",
    correctAnswer: "",
    analysis: "",
    bbox: { x1: 0, y1: 0, x2: 0, y2: 0 },
    manualWrong: "auto",
    manualWrongLabel: "按高置信批改结果；不确定时不自动建错题",
    manualWrongOptions: ["按置信度", "教师确认是错题", "教师确认不是错题"],
    cropPath: "",
    loading: false,
    busy: false,
    accuracyStatus: "PENDING_REVIEW",
    errorMessage: "",
    notice: ""
  },

  onShow: function () {
    if (!auth.guardRole(this, "teacher")) return;
    if (!this.data.classes.length) this.loadClasses();
    else this.loadClassMistakes();
  },

  loadClasses: function () {
    this.setData({ loading: true, errorMessage: "" });
    return api.teacherClasses().then(function (classes) {
      classes = classes || [];
      this.setData({ classes: classes, classId: classes.length ? classes[0].id : 0, classIndex: 0 });
      if (classes.length) return this.loadAssignments();
      this.setData({ loading: false });
    }.bind(this)).catch(function (error) {
      this.setData({ loading: false, errorMessage: error.message || "班级读取失败" });
    }.bind(this));
  },

  onClassChange: function (event) {
    const index = Number(event.detail.value || 0);
    const classroom = this.data.classes[index];
    this.setData({ classIndex: index, classId: classroom ? classroom.id : 0, assignmentId: 0, taskId: "" });
    this.loadAssignments();
  },

  loadAssignments: function () {
    if (!this.data.classId) return Promise.resolve();
    this.setData({ loading: true, assignments: [], submissions: [], eligibleSubmissions: [], sources: [] });
    return api.teacherAssignments(this.data.classId).then(function (assignments) {
      assignments = (assignments || []).map(function (item) {
        item.displayTitle = item.title + " · " + (item.assignment_date || "未设日期");
        return item;
      });
      this.setData({ assignments: assignments, assignmentIndex: 0, assignmentId: assignments.length ? assignments[0].id : 0 });
      if (assignments.length) return this.loadSubmissions();
      this.setData({ loading: false });
      return this.loadClassMistakes();
    }.bind(this)).catch(function (error) {
      this.setData({ loading: false, errorMessage: error.message || "作业列表读取失败" });
    }.bind(this));
  },

  onAssignmentChange: function (event) {
    const index = Number(event.detail.value || 0);
    const assignment = this.data.assignments[index];
    this.setData({ assignmentIndex: index, assignmentId: assignment ? assignment.id : 0, taskId: "" });
    this.loadSubmissions();
  },

  loadSubmissions: function () {
    if (!this.data.assignmentId) return Promise.resolve();
    this.setData({ loading: true, submissions: [], eligibleSubmissions: [], sources: [], taskId: "" });
    return api.assignmentSubmissions(this.data.assignmentId).then(function (items) {
      const eligible = (items || []).filter(function (item) {
        return item.task_id && item.task_status === "SUCCESS";
      }).map(function (item) {
        item.displayLabel = (item.student_name || "学生") + " · " + item.task_id;
        return item;
      });
      this.setData({
        submissions: items || [],
        eligibleSubmissions: eligible,
        submissionIndex: 0,
        taskId: eligible.length ? eligible[0].task_id : "",
        loading: false
      });
      const requests = [this.loadClassMistakes()];
      if (eligible.length) requests.push(this.loadTaskAssets());
      return Promise.all(requests);
    }.bind(this)).catch(function (error) {
      this.setData({ loading: false, errorMessage: error.message || "提交列表读取失败" });
    }.bind(this));
  },

  onSubmissionChange: function (event) {
    const index = Number(event.detail.value || 0);
    const submission = this.data.eligibleSubmissions[index];
    this.setData({ submissionIndex: index, taskId: submission ? submission.task_id : "", sources: [] });
    if (submission) this.loadTaskAssets();
  },

  runDigitize: function () {
    if (!this.data.taskId) return;
    this.setData({ busy: true, errorMessage: "", notice: "" });
    api.digitizePaperTask(this.data.taskId).then(function (result) {
      this.setData({ accuracyStatus: result.accuracy_status || "PENDING_REVIEW" });
      this.setData({ notice: "已生成或重用待校对候选；模型未确认内容不会自动入错题。" });
      return this.loadTaskAssets();
    }.bind(this)).catch(function (error) {
      this.setData({ errorMessage: error.message || "切题候选生成失败，原图仍保留" });
    }.bind(this)).then(function () {
      this.setData({ busy: false });
    }.bind(this));
  },

  loadTaskAssets: function () {
    if (!this.data.taskId) return Promise.resolve();
    this.setData({ loading: true, errorMessage: "" });
    return api.paperTaskAssets(this.data.taskId).then(function (result) {
      const sources = result.sources || [];
      this.setData({
        sources: sources,
        accuracyStatus: result.accuracy_status || "PENDING_REVIEW",
        loading: false
      });
      if (sources.length) this.selectSourceById(sources[0].source_id);
    }.bind(this)).catch(function (error) {
      this.setData({ loading: false, sources: [], errorMessage: error.message || "题目候选读取失败" });
    }.bind(this));
  },

  selectSource: function (event) {
    this.selectSourceById(Number(event.currentTarget.dataset.id));
  },

  selectSourceById: function (sourceId) {
    const source = this.data.sources.find(function (item) { return item.source_id === sourceId; });
    if (!source) return;
    api.paperTaskAssets(this.data.taskId).then(function (result) {
      const candidates = (result.grading_results || []).filter(function (item) {
        return item.image_index === source.page_index;
      });
      let selected = source.grading_result || null;
      if (!selected && source.question_no) {
        selected = candidates.find(function (item) { return String(item.question_no) === String(source.question_no); });
      }
      if (!selected && candidates.length) selected = candidates[0];
      const options = candidates.map(function (item) {
        item.displayLabel = "题 " + item.question_no + " · " + item.result + " · 置信 " + (item.confidence == null ? "未知" : item.confidence);
        return item;
      });
      const index = selected ? options.findIndex(function (item) { return item.id === selected.id; }) : -1;
      this.setData({
        selectedSourceId: source.source_id,
        selectedSource: source,
        gradingOptions: options,
        gradingIndex: Math.max(0, index),
        gradingResultId: selected ? selected.id : 0,
        questionNo: source.question_no || (selected ? selected.question_no : ""),
        questionText: (source.question && source.question.question_text) || (selected && selected.question_text) || "",
        questionType: (source.question && source.question.question_type) || (selected && selected.question_type) || "",
        correctAnswer: (source.question && source.question.correct_answer) || (selected && selected.correct_answer) || "",
        analysis: (source.question && source.question.analysis) || (selected && selected.analysis) || "",
        bbox: source.bbox,
        cropPath: ""
      });
      api.downloadPaperImage(source.crop_url).then(function (filePath) {
        this.setData({ cropPath: filePath });
      }.bind(this)).catch(function () {
        this.setData({ errorMessage: "裁切图暂时无法读取，请核对原作业。" });
      }.bind(this));
    }.bind(this)).catch(function (error) {
      this.setData({ errorMessage: error.message || "批改题目关联读取失败" });
    }.bind(this));
  },

  onGradingChange: function (event) {
    const index = Number(event.detail.value || 0);
    const result = this.data.gradingOptions[index];
    if (!result) return;
    this.setData({
      gradingIndex: index,
      gradingResultId: result.id,
      questionNo: result.question_no || "",
      questionText: result.question_text || "",
      questionType: result.question_type || "",
      correctAnswer: result.correct_answer || "",
      analysis: result.analysis || ""
    });
  },

  onFieldInput: function (event) {
    const key = event.currentTarget.dataset.key;
    const update = {};
    update[key] = event.detail.value;
    this.setData(update);
  },

  onBoxInput: function (event) {
    const key = event.currentTarget.dataset.key;
    const update = {};
    update["bbox." + key] = Number(event.detail.value || 0);
    this.setData(update);
  },

  onWrongChange: function (event) {
    const values = ["auto", "yes", "no"];
    const labels = ["按高置信批改结果；不确定时不自动建错题", "教师确认是错题", "教师确认不是错题"];
    const index = Number(event.detail.value || 0);
    this.setData({ manualWrong: values[index], manualWrongLabel: labels[index] });
  },

  saveReview: function () {
    const source = this.data.selectedSource;
    if (!source || !this.data.gradingResultId) {
      this.setData({ errorMessage: "当前候选未关联本页批改题，请先生成并选择可用结果。" });
      return;
    }
    this.setData({ busy: true, errorMessage: "", notice: "" });
    api.reviewPaperSource(source.source_id, {
      grading_result_id: this.data.gradingResultId,
      question_no: this.data.questionNo || null,
      question_text: this.data.questionText,
      question_type: this.data.questionType || null,
      correct_answer: this.data.correctAnswer || null,
      analysis: this.data.analysis || null,
      x1: Number(this.data.bbox.x1), y1: Number(this.data.bbox.y1),
      x2: Number(this.data.bbox.x2), y2: Number(this.data.bbox.y2),
      manual_wrong: this.data.manualWrong === "auto" ? null : this.data.manualWrong === "yes",
      confirm: true
    }).then(function (result) {
      this.setData({ notice: result.mistake_created ? "题目已确认并进入学生错题集。" : (result.mistake_status_reason || "题目来源已确认。") });
      return Promise.all([this.loadTaskAssets(), this.loadClassMistakes()]);
    }.bind(this)).catch(function (error) {
      this.setData({ errorMessage: error.message || "题目校对未保存" });
    }.bind(this)).then(function () {
      this.setData({ busy: false });
    }.bind(this));
  },

  loadClassMistakes: function () {
    if (!this.data.classId) return Promise.resolve();
    return api.classMistakes(this.data.classId).then(function (response) {
      const mistakes = (response.items || []).map(function (item) {
        item.expanded = false;
        item.attempts = [];
        item.feedback = "";
        if (item.question) item.question.knowledge_points_label = (item.question.knowledge_points || []).join("、");
        return item;
      });
      this.setData({ mistakes: mistakes });
    }.bind(this)).catch(function () { this.setData({ mistakes: [] }); }.bind(this));
  },

  toggleHistory: function (event) {
    const id = Number(event.currentTarget.dataset.id);
    const index = this.data.mistakes.findIndex(function (item) { return item.id === id; });
    if (index < 0) return;
    const item = this.data.mistakes[index];
    if (item.expanded) {
      const update = {};
      update["mistakes[" + index + "].expanded"] = false;
      this.setData(update);
      return;
    }
    api.correctionHistory(id).then(function (response) {
      const update = {};
      update["mistakes[" + index + "].attempts"] = response.items || [];
      update["mistakes[" + index + "].expanded"] = true;
      this.setData(update);
    }.bind(this)).catch(function (error) {
      this.setData({ errorMessage: error.message || "订正记录读取失败" });
    }.bind(this));
  },

  openMistakeSource: function (event) {
    const mistakeId = Number(event.currentTarget.dataset.id);
    const item = this.data.mistakes.find(function (row) { return row.id === mistakeId; });
    if (!item || !item.source_id) {
      this.setData({ errorMessage: "该错题没有可回溯的题目来源。" });
      return;
    }
    this.setData({ taskId: item.source_task_id, loading: true, errorMessage: "" });
    api.paperTaskAssets(item.source_task_id).then(function (result) {
      this.setData({ sources: result.sources || [], loading: false, accuracyStatus: result.accuracy_status || "PENDING_REVIEW" });
      this.selectSourceById(item.source_id);
    }.bind(this)).catch(function (error) {
      this.setData({ loading: false, errorMessage: error.message || "题目来源读取失败" });
    }.bind(this));
  },

  onFeedbackInput: function (event) {
    const id = Number(event.currentTarget.dataset.id);
    const index = this.data.mistakes.findIndex(function (item) { return item.id === id; });
    if (index < 0) return;
    const update = {};
    update["mistakes[" + index + "].feedback"] = event.detail.value;
    this.setData(update);
  },

  reviewStudentCorrection: function (event) {
    const mistakeId = Number(event.currentTarget.dataset.mistake);
    const attemptId = Number(event.currentTarget.dataset.attempt);
    const accepted = String(event.currentTarget.dataset.accepted) === "true";
    const item = this.data.mistakes.find(function (row) { return row.id === mistakeId; });
    api.reviewCorrection(mistakeId, attemptId, accepted, item ? item.feedback : "").then(function () {
      this.setData({ notice: accepted ? "订正已通过。" : "已退回订正，学生可重新提交。" });
      return this.loadClassMistakes();
    }.bind(this)).catch(function (error) {
      this.setData({ errorMessage: error.message || "教师复核失败" });
    }.bind(this));
  },

  previewSource: function (event) {
    const kind = event.currentTarget.dataset.kind || "crop";
    const source = this.data.selectedSource;
    if (!source) return;
    api.downloadPaperImage(kind === "original" ? source.original_url : source.crop_url).then(function (path) {
      wx.previewImage({ current: path, urls: [path] });
    }).catch(function (error) { this.setData({ errorMessage: error.message || "图片读取失败" }); }.bind(this));
  }
});
