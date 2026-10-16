const api = require("../../../utils/api");
const auth = require("../../../utils/auth");
const display = require("../../../utils/display");

Page({
  data: {
    currentUser: null,
    taskId: "",
    status: "PENDING",
    statusLabel: "等待批改",
    result: null,
    errorMessage: "",
    canRetry: false,
    retryBusy: false,
    loading: true
  },

  onLoad: function (options) {
    this.taskId = options.task_id ? decodeURIComponent(options.task_id) : "";
    this.pollDeadline = Date.now() + 180000;
    this.setData({ taskId: this.taskId });
  },

  onShow: function () {
    if (!auth.guardRole(this, "student")) return;
    if (this.taskId) this.pollStatus();
  },

  onHide: function () {
    this.stopPolling();
  },

  onUnload: function () {
    this.stopPolling();
  },

  stopPolling: function () {
    if (this.pollTimer) {
      clearTimeout(this.pollTimer);
      this.pollTimer = null;
    }
  },

  pollStatus: function () {
    this.stopPolling();
    if (Date.now() >= this.pollDeadline) {
      this.setData({
        loading: false,
        errorMessage: "处理时间已超过等待上限，任务状态未知。请手动刷新状态；系统不会自动重复调用模型。"
      });
      return;
    }
    api.taskStatus(this.taskId).then(function (status) {
      const label = display.statusLabel(status.status);
      this.setData({
        status: status.status,
        statusLabel: label,
        canRetry: !!status.can_retry,
        failureMessage: status.failure_message || ""
      });
      if (status.status === "SUCCESS") {
        this.loadResult();
        return;
      }
      if (status.status === "WAIT_REVIEW" || status.status === "UNKNOWN_LAYOUT") {
        this.setData({ loading: false, canRetry: false, errorMessage: status.status === "WAIT_REVIEW"
          ? "本地括号识别已结束，等待教师确认。未确认项不计为错题，无需重复提交。"
          : "照片未能与本次作业模板完整匹配。请返回原作业核对页面并重新拍照提交，或联系教师检查模板。不会自动调用付费模型。" });
        return;
      }
      if (status.status === "FAILED") {
        this.setData({
          loading: false,
          errorMessage: status.failure_message || "本次批改未完成，未生成有效结果。"
        });
        return;
      }
      this.pollTimer = setTimeout(function () { this.pollStatus(); }.bind(this), 2500);
    }.bind(this)).catch(function (error) {
      this.setData({ loading: false, errorMessage: error.message || "读取批改状态失败" });
    }.bind(this));
  },

  refreshStatus: function () {
    this.pollDeadline = Date.now() + 180000;
    this.setData({ loading: true, errorMessage: "" });
    this.pollStatus();
  },

  retryTask: function () {
    if (!this.data.canRetry || this.data.retryBusy) return;
    wx.showModal({
      title: "确认重新批改",
      content: "上次请求可能已被模型服务处理，重新批改可能再次计费。系统不会自动重试。是否继续？",
      confirmText: "确认重试",
      success: function (res) {
        if (!res.confirm) return;
        this.setData({ retryBusy: true, errorMessage: "" });
        api.retryHomework(this.taskId).then(function () {
          this.pollDeadline = Date.now() + 180000;
          this.setData({ status: "PENDING", statusLabel: "已重新排队", loading: true, canRetry: false });
          this.pollStatus();
        }.bind(this)).catch(function (error) {
          this.setData({ loading: false, errorMessage: error.message || "任务重试失败" });
        }.bind(this)).then(function () {
          this.setData({ retryBusy: false });
        }.bind(this));
      }.bind(this)
    });
  },

  openMistakes: function () {
    wx.navigateTo({ url: "/pages/student/mistakes/mistakes" });
  },

  loadResult: function () {
    api.studentResult(this.taskId).then(function (result) {
      const rows = (result.results || []).map(function (row) {
        row.outcome = row.result === "correct" ? "正确"
          : row.result === "partial" ? "部分正确"
            : row.result === "wrong" ? "错误" : row.result;
        row.outcomeClass = row.result === "correct" ? "result-correct"
          : row.result === "wrong" ? "result-wrong" : "result-partial";
        return row;
      });
      result.results = rows;
      this.setData({ result: result, loading: false, errorMessage: "" });
    }.bind(this)).catch(function (error) {
      this.setData({ loading: false, errorMessage: error.message || "读取批改结果失败" });
    }.bind(this));
  },

  goBack: function () {
    wx.navigateBack({ delta: 1 });
  }
});
