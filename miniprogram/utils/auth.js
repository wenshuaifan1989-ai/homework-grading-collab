function getSession() {
  return {
    token: wx.getStorageSync("access_token") || "",
    user: wx.getStorageSync("current_user") || null
  };
}

function homeForRole(role) {
  if (role === "admin") return "/pages/admin/home/home";
  return role === "teacher"
    ? "/pages/teacher/home/home"
    : "/pages/student/homework/homework";
}

function guardRole(page, role, allowUnbound) {
  const session = getSession();
  if (!session.token || !session.user) {
    wx.reLaunch({ url: "/pages/login/login" });
    return false;
  }
  // Family-linked students can be used by any authenticated account; the API
  // still limits the returned students and assignments to active bindings.
  if (session.user.role !== role && role !== "student") {
    wx.reLaunch({ url: homeForRole(session.user.role) });
    return false;
  }
  if (role === "student" && session.user.bind_status === "unbound" && !allowUnbound) {
    wx.reLaunch({ url: "/pages/student/bind/bind" });
    return false;
  }
  page.setData({ currentUser: session.user });
  return true;
}

function logout() {
  const app = getApp();
  app.clearSession();
  wx.reLaunch({ url: "/pages/login/login" });
}

module.exports = {
  getSession: getSession,
  homeForRole: homeForRole,
  guardRole: guardRole,
  logout: logout
};
