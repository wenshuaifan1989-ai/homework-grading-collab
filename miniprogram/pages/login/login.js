const api = require("../../utils/api");
const auth = require("../../utils/auth");

Page({
  data: {
    phone: "",
    password: "",
    fullName: "",
    registerMode: false,
    submitting: false,
    wechatProfileMode: false
  },

  onLoad: function () {
    const session = auth.getSession();
    if (session.token && session.user) {
      const route = function (user) {
        wx.reLaunch({
          url: user.role === "student" && user.bind_status === "unbound"
            ? "/pages/student/bind/bind"
            : auth.homeForRole(user.role)
        });
      };
      api.myProfile().then(function (profile) {
        getApp().saveSession(session.token, profile);
        route(profile);
      }).catch(function () {
        // request.js clears an unauthorized session; remain on this login page.
        getApp().clearSession();
      });
    }
  },

  onPhoneInput: function (event) {
    this.setData({ phone: (event.detail.value || "").trim() });
  },

  onPasswordInput: function (event) {
    this.setData({ password: event.detail.value || "" });
  },

  onFullNameInput: function (event) {
    this.setData({ fullName: (event.detail.value || "").trim() });
  },

  continueForUser: function (user) {
    if (user.role === "student" && user.bind_status === "unbound") {
      wx.reLaunch({ url: "/pages/student/bind/bind" });
    } else {
      wx.reLaunch({ url: auth.homeForRole(user.role) });
    }
  },

  loginWithWechat: function () {
    if (this.data.submitting) return;
    this.setData({ submitting: true });
    new Promise(function (resolve, reject) {
      wx.login({ success: resolve, fail: reject });
    }).then(function (result) {
        if (!result || !result.code) {
          throw new Error("微信登录凭证获取失败");
        }
        return api.wechatLogin(result.code);
    }).then(function (response) {
      if (!response || !response.access_token || !response.user) {
        throw new Error("微信登录响应缺少账号信息");
      }
      getApp().saveSession(response.access_token, response.user);
      if (response.user.profile_complete) {
        this.continueForUser(response.user);
      } else {
        this.setData({
          wechatProfileMode: true,
          phone: response.user.phone || "",
          fullName: response.user.full_name || ""
        });
      }
    }.bind(this)).catch(function (error) {
      wx.showToast({ title: error.message || "微信登录失败", icon: "none" });
    }).then(function () {
      this.setData({ submitting: false });
    }.bind(this));
  },

  onWechatPhone: function (event) {
    const detail = event.detail || {};
    if (detail.errMsg !== "getPhoneNumber:ok" || !detail.code) {
      wx.showToast({ title: "手机号授权已跳过，可手工填写或稍后补充", icon: "none" });
      return;
    }
    api.wechatPhone(detail.code).then(function (user) {
      const session = auth.getSession();
      getApp().saveSession(session.token, user);
      this.setData({ phone: user.phone || "" });
      wx.showToast({ title: "手机号已绑定", icon: "success" });
    }.bind(this)).catch(function (error) {
      wx.showToast({ title: error.message || "手机号绑定失败", icon: "none" });
    });
  },

  saveWechatProfile: function () {
    const profile = { full_name: this.data.fullName };
    if (this.data.phone) profile.phone = this.data.phone;
    api.updateMyProfile(profile).then(function (user) {
      const session = auth.getSession();
      getApp().saveSession(session.token, user);
      if (user.profile_complete) {
        this.continueForUser(user);
      } else {
        wx.showToast({ title: "资料已保存，手机号可稍后补充", icon: "none" });
      }
    }.bind(this)).catch(function (error) {
      wx.showToast({ title: error.message || "资料保存失败", icon: "none" });
    });
  },

  skipWechatProfile: function () {
    const session = auth.getSession();
    if (session.user) this.continueForUser(session.user);
  },

  toggleRegister: function () {
    this.setData({ registerMode: !this.data.registerMode });
  },

  login: function () {
    const phone = this.data.phone;
    const password = this.data.password;
    if (!phone || !password) {
      wx.showToast({ title: "请输入手机号和密码", icon: "none" });
      return;
    }
    if (this.data.registerMode && !this.data.fullName) {
      wx.showToast({ title: "请输入学生姓名", icon: "none" });
      return;
    }
    if (this.data.submitting) return;
    this.setData({ submitting: true });

    const action = this.data.registerMode
      ? api.registerStudent(phone, password, this.data.fullName)
      : api.login(phone, password);
    action.then(function (response) {
      if (this.data.registerMode) return api.login(phone, password);
      return response;
    }.bind(this)).then(function (response) {
      if (!response || !response.access_token || !response.user) {
        throw new Error("登录响应缺少账号信息");
      }
      if (response.user.role !== "teacher" && response.user.role !== "student" && response.user.role !== "admin") {
        throw new Error("当前账号角色不受支持");
      }
      getApp().saveSession(response.access_token, response.user);
      if (response.user.wechat_bind_status !== "bound") {
        this.setData({
          wechatProfileMode: true,
          phone: response.user.phone || "",
          fullName: response.user.full_name || ""
        });
      } else {
        this.continueForUser(response.user);
      }
    }.bind(this)).catch(function (error) {
      wx.showToast({ title: error.message || "登录失败", icon: "none", duration: 2600 });
    }).then(function () {
      this.setData({ submitting: false });
    }.bind(this));
  }
});
