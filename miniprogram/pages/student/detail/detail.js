const api = require("../../../utils/api");
const auth = require("../../../utils/auth");
const display = require("../../../utils/display");
const request = require("../../../utils/request");

Page({
  data: {
    currentUser: null,
    assignment: null,
    loading: true
  },

  onLoad: function (options) {
    this.assignmentId = Number(options.id);
    this.studentId = Number(options.student_id || wx.getStorageSync("active_student_id") || 0);
  },

  onShow: function () {
    if (auth.guardRole(this, "student")) this.loadAssignment();
  },

  loadAssignment: function () {
    api.studentAssignments(this.studentId).then(function (items) {
      const assignment = (items || []).find(function (item) {
        return Number(item.id) === this.assignmentId;
      }.bind(this));
      if (!assignment) throw new Error("作业不存在或当前账号无权查看");
      assignment.dueLabel = display.dateLabel(assignment.due_at);
      assignment.taskStatusLabel = display.statusLabel(assignment.task_status);
      this.setData({ assignment: assignment, loading: false });
    }.bind(this)).catch(function (error) {
      this.setData({ loading: false });
      wx.showToast({ title: error.message || "作业加载失败", icon: "none" });
    }.bind(this));
  },

  openSubmit: function () {
    const assignment = this.data.assignment;
    if (assignment && assignment.submitted && assignment.task_status !== "UNKNOWN_LAYOUT") {
      wx.showToast({ title: "这份作业已有提交，请查看原任务状态", icon: "none" });
      return;
    }
    if (assignment && assignment.variant_mode && !assignment.variant_available) {
      wx.showToast({ title: assignment.variant_message || "老师尚未准备好本次练习", icon: "none" });
      return;
    }
    wx.navigateTo({
      url: "/pages/student/submit/submit?id=" + this.assignmentId +
        "&student_id=" + encodeURIComponent(this.studentId || "")
    });
  },

  openOriginal: function () {
    const format=this.data.assignment.original_format;
    request.download('/api/v1/teacher-v2/assignments/'+this.assignmentId+'/source?student_id='+this.studentId)
      .then(function(path){
        if(['png','jpg','jpeg'].indexOf(format)>=0) wx.previewImage({urls:[path]});
        else wx.openDocument({filePath:path,fileType:format==='docx'?'docx':'pdf',showMenu:true});
      }).catch(function(e){wx.showToast({title:e.message||'原卷读取失败',icon:'none'});});
  },

  openResult: function () {
    const assignment = this.data.assignment;
    if (!assignment || !assignment.task_id) return;
    wx.navigateTo({
      url: "/pages/student/result/result?task_id=" +
        encodeURIComponent(assignment.task_id)
    });
  }
});
