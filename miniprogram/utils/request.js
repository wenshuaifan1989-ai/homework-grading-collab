const config = require("./config");

function appInstance() {
  try {
    return getApp();
  } catch (e) {
    return null;
  }
}

function clearOnUnauthorized() {
  const app = appInstance();
  if (app && app.clearSession) app.clearSession();
  wx.reLaunch({ url: "/pages/login/login" });
}

function errorMessage(body, statusCode) {
  if (body && typeof body === "object") {
    return body.detail || body.message || ("请求失败（" + statusCode + "）");
  }
  return "请求失败（" + statusCode + "）";
}

function unwrap(body) {
  if (body && Object.prototype.hasOwnProperty.call(body, "data")) {
    return body.data;
  }
  return body;
}

function request(path, method, data, options) {
  const opts = options || {};
  const token = wx.getStorageSync("access_token");
  // 本地调试用：ngrok 免费版会给"浏览器式"请求的 GET 注入警告页
  // （返回 HTTP 200 + text/html），带上此头即跳过，保证拿到真实 JSON。
  const header = Object.assign(
    { "Content-Type": "application/json", "ngrok-skip-browser-warning": "1" },
    opts.header || {}
  );
  if (token && opts.auth !== false) header.Authorization = "Bearer " + token;

  return new Promise(function (resolve, reject) {
    wx.request({
      url: config.BASE_URL + path,
      method: method || "GET",
      data: data,
      header: header,
      timeout: opts.timeout || 30000,
      success: function (res) {
        if (res.statusCode === 401 && opts.auth !== false) {
          clearOnUnauthorized();
          reject(new Error("登录已过期，请重新登录"));
          return;
        }
        if (res.statusCode < 200 || res.statusCode >= 300) {
          reject(new Error(errorMessage(res.data, res.statusCode)));
          return;
        }
        resolve(unwrap(res.data));
      },
      fail: function (err) {
        reject(new Error(err.errMsg || "网络连接失败，请检查服务地址"));
      }
    });
  });
}

function download(path, options) {
  const opts = options || {};
  const token = wx.getStorageSync("access_token");
  const header = Object.assign({}, opts.header || {});
  if (token && opts.auth !== false) header.Authorization = "Bearer " + token;
  return new Promise(function (resolve, reject) {
    wx.downloadFile({
      url: config.BASE_URL + path,
      header: header,
      timeout: opts.timeout || 30000,
      success: function (res) {
        if (res.statusCode === 401 && opts.auth !== false) {
          clearOnUnauthorized();
          reject(new Error("登录已过期，请重新登录"));
          return;
        }
        if (res.statusCode < 200 || res.statusCode >= 300) {
          reject(new Error("图片读取失败（" + res.statusCode + "）"));
          return;
        }
        resolve(res.tempFilePath);
      },
      fail: function (err) {
        reject(new Error(err.errMsg || "图片读取失败"));
      }
    });
  });
}

module.exports = {
  request: request,
  get: function (path, options) {
    return request(path, "GET", undefined, options);
  },
  post: function (path, data, options) {
    return request(path, "POST", data, options);
  },
  download: download
};
