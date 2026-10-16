function statusLabel(status) {
  const labels = {
    PENDING: "等待批改",
    PROCESSING: "AI 批改中",
    PREPROCESSING: "图片处理中",
    GRADING: "AI 批改中",
    SUCCESS: "批改完成",
    WAIT_REVIEW: "答案识别待教师复核",
    UNKNOWN_LAYOUT: "页面未匹配，请联系教师或重拍",
    FAILED: "批改失败"
  };
  return labels[status] || status || "待提交";
}

function dateLabel(value) {
  if (!value) return "未设置";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = function (n) { return n < 10 ? "0" + n : String(n); };
  return date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" +
    pad(date.getDate()) + " " + pad(date.getHours()) + ":" + pad(date.getMinutes());
}

function isTerminal(status) {
  return status === "SUCCESS" || status === "FAILED" || status === "WAIT_REVIEW" || status === "UNKNOWN_LAYOUT";
}

module.exports = {
  statusLabel: statusLabel,
  dateLabel: dateLabel,
  isTerminal: isTerminal
};
