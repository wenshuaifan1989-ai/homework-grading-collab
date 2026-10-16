// 本机微信开发者工具调试地址；仅用于本地模拟器，不用于真机或生产。
// 真实微信登录仍需有效 AppID/服务端凭据，不在此处模拟 OpenID。
const BASE_URL = "http://127.0.0.1:8000";

module.exports = {
  BASE_URL: BASE_URL.replace(/\/+$/, "")
};
