const config = require("./config");

function utf8(value) {
  const encoded = unescape(encodeURIComponent(value));
  const bytes = new Uint8Array(encoded.length);
  for (let i = 0; i < encoded.length; i += 1) {
    bytes[i] = encoded.charCodeAt(i);
  }
  return bytes;
}

function readFile(filePath) {
  return new Promise(function (resolve, reject) {
    wx.getFileSystemManager().readFile({
      filePath: filePath,
      success: function (res) {
        resolve(new Uint8Array(res.data));
      },
      fail: function (err) {
        reject(new Error(err.errMsg || "读取图片失败"));
      }
    });
  });
}

function mimeFor(path) {
  const ext = (path.split(".").pop() || "").toLowerCase();
  if (ext === "png") return "image/png";
  if (ext === "webp") return "image/webp";
  if (ext === "gif") return "image/gif";
  return "image/jpeg";
}

function concat(parts) {
  let length = 0;
  parts.forEach(function (part) { length += part.byteLength; });
  const result = new Uint8Array(length);
  let offset = 0;
  parts.forEach(function (part) {
    result.set(part, offset);
    offset += part.byteLength;
  });
  return result.buffer;
}

function buildMultipart(files, fields, boundary) {
  const chunks = [];
  Object.keys(fields).forEach(function (key) {
    if (fields[key] === undefined || fields[key] === null || fields[key] === "") return;
    chunks.push(utf8("--" + boundary + "\r\n"));
    chunks.push(utf8('Content-Disposition: form-data; name="' + key + '"\r\n\r\n'));
    chunks.push(utf8(String(fields[key]) + "\r\n"));
  });
  return Promise.all(files.map(function (file) {
    return readFile(file.path);
  })).then(function (fileBuffers) {
    fileBuffers.forEach(function (bytes, index) {
      const file = files[index];
      const filename = "homework_" + (index + 1) + "." +
        ((file.path.split(".").pop() || "jpg").toLowerCase().replace(/[^a-z0-9]/g, "") || "jpg");
      chunks.push(utf8("--" + boundary + "\r\n"));
      chunks.push(utf8('Content-Disposition: form-data; name="files"; filename="' + filename + '"\r\n'));
      chunks.push(utf8("Content-Type: " + mimeFor(file.path) + "\r\n\r\n"));
      chunks.push(bytes);
      chunks.push(utf8("\r\n"));
    });
    chunks.push(utf8("--" + boundary + "--\r\n"));
    return concat(chunks);
  });
}

function upload(path, files, fields, idempotencyKey) {
  const boundary = "----wxHomework" + Date.now().toString(16) +
    Math.random().toString(16).slice(2);
  const token = wx.getStorageSync("access_token");
  const form = Object.assign({}, fields || {});

  return buildMultipart(files, form, boundary).then(function (body) {
    return new Promise(function (resolve, reject) {
      wx.request({
        url: config.BASE_URL + path,
        method: "POST",
        data: body,
        timeout: 120000,
        header: {
          "Content-Type": "multipart/form-data; boundary=" + boundary,
          Authorization: "Bearer " + token,
          "Idempotency-Key": idempotencyKey || ""
        },
        success: function (res) {
          if (res.statusCode === 401) {
            const app = getApp();
            if (app && app.clearSession) app.clearSession();
            wx.reLaunch({ url: "/pages/login/login" });
            reject(new Error("登录已过期，请重新登录"));
            return;
          }
          if (res.statusCode < 200 || res.statusCode >= 300) {
            const bodyData = res.data || {};
            reject(new Error(bodyData.detail || bodyData.message || ("提交失败（" + res.statusCode + "）")));
            return;
          }
          resolve(res.data && Object.prototype.hasOwnProperty.call(res.data, "data")
            ? res.data.data : res.data);
        },
        fail: function (err) {
          reject(new Error(err.errMsg || "提交失败，请检查网络"));
        }
      });
    });
  });
}

module.exports = {
  upload: upload
};
