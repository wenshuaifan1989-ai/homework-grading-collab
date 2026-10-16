const assert = require("assert");

let clearCount = 0;
let relaunchCount = 0;
let lastUrl = "";
const storage = {};
let toasts = [];
let savedSession = null;

global.getApp = function () {
  return {
    clearSession: function () {
      clearCount += 1;
      delete storage.access_token;
      delete storage.current_user;
    },
    saveSession: function (token, user) {
      savedSession = { token: token, user: user };
      storage.access_token = token;
      storage.current_user = user;
    }
  };
};
global.wx = {
  getStorageSync: function (key) { return storage[key] || ""; },
  setStorageSync: function (key, value) { storage[key] = value; },
  removeStorageSync: function (key) { delete storage[key]; },
  showToast: function (options) { toasts.push(options.title); },
  login: function (options) { options.success({ code: "one-time-code" }); },
  reLaunch: function (options) {
    relaunchCount += 1;
    lastUrl = options.url;
  },
  request: function (options) {
    options.success({
      statusCode: 401,
      data: { detail: "账号或密码错误" }
    });
  }
};

const request = require("../miniprogram/utils/request");

async function run() {
  await assert.rejects(
    request.post("/api/v1/users/login", {}, { auth: false }),
    /账号或密码错误/
  );
  assert.strictEqual(clearCount, 0, "auth:false 401 must not clear session");
  assert.strictEqual(relaunchCount, 0, "auth:false 401 must not relaunch login page");

  await assert.rejects(request.get("/api/v1/classes/mine"), /登录已过期/);
  assert.strictEqual(clearCount, 1, "authenticated 401 clears the session once");
  assert.strictEqual(relaunchCount, 1, "authenticated 401 relaunches login once");
  assert.strictEqual(lastUrl, "/pages/login/login");

  let profileBehavior = function () { return Promise.reject(new Error("token expired")); };
  let wechatBehavior = function () {
    return Promise.resolve({
      access_token: "test-only-access-token-005",
      user: { id: 9, role: "student", profile_complete: false, phone: null, full_name: null }
    });
  };
  const apiPath = require.resolve("../miniprogram/utils/api");
  require(apiPath);
  require.cache[apiPath].exports = {
    login: function () { return Promise.reject(new Error("账号或密码错误")); },
    registerStudent: function () { return Promise.resolve({}); },
    myProfile: function () { return profileBehavior(); },
    wechatLogin: function (code) {
      assert.strictEqual(code, "one-time-code");
      return wechatBehavior();
    }
  };
  let loginPage;
  global.Page = function (definition) { loginPage = definition; };
  require(require.resolve("../miniprogram/pages/login/login.js"));
  const waitTurn = function () { return new Promise(function (resolve) { setTimeout(resolve, 0); }); };

  loginPage.data = Object.assign({}, loginPage.data, { phone: (('' + "138" + '00000001')), password: "test-only-password-006" });
  loginPage.setData = function (update) { Object.assign(this.data, update); };
  loginPage.login.call(loginPage);
  await waitTurn();
  assert.strictEqual(loginPage.data.phone, (('' + "138" + '00000001')), "wrong password preserves phone input");
  assert.strictEqual(loginPage.data.password, "test-only-password-006", "wrong password preserves password input");
  assert.ok(toasts.includes("账号或密码错误"), "wrong password displays backend detail");

  storage.access_token = "test-only-access-token-007";
  storage.current_user = { id: 7, role: "teacher" };
  loginPage.onLoad.call(loginPage);
  await waitTurn();
  assert.strictEqual(storage.access_token, undefined, "stale token is removed");
  assert.strictEqual(relaunchCount, 1, "profile rejection does not create another redirect loop");

  storage.access_token = "test-only-access-token-008";
  storage.current_user = { id: 8, role: "teacher" };
  profileBehavior = function () { return Promise.resolve({ id: 8, role: "teacher" }); };
  loginPage.onLoad.call(loginPage);
  await waitTurn();
  assert.strictEqual(savedSession.user.id, 8, "valid profile is saved");
  assert.strictEqual(lastUrl, "/pages/teacher/home/home", "valid teacher enters teacher home");

  loginPage.data.submitting = false;
  loginPage.data.wechatProfileMode = false;
  loginPage.loginWithWechat.call(loginPage);
  await waitTurn();
  assert.strictEqual(savedSession.user.id, 9, "first WeChat login saves the returned identity");
  assert.strictEqual(loginPage.data.wechatProfileMode, true, "incomplete profile can be completed after login");
  assert.strictEqual(lastUrl, "/pages/teacher/home/home", "incomplete profile does not redirect prematurely");
  process.stdout.write("009A_MINIPROGRAM_AUTH_PASS\n");
}

run().catch(function (error) {
  process.stderr.write(String(error && error.stack || error) + "\n");
  process.exitCode = 1;
});
