const assert = require("assert");

const requests = [];
let activeUser = { id: 9, role: "teacher" };
let relaunches = 0;
global.wx = {
  getStorageSync: function (key) {
    if (key === "access_token") return "test-token";
    if (key === "current_user") return activeUser;
    return null;
  },
  setStorageSync: function () {},
  reLaunch: function () { relaunches += 1; },
  getFileSystemManager: function () {
    return {
      readFile: function (options) {
        options.success({ data: Uint8Array.from([1, 2, 3]).buffer });
      }
    };
  },
  request: function (options) {
    requests.push(options);
    options.success({ statusCode: 200, data: { data: { task_id: "task-test" } } });
  }
};
global.getApp = function () { return { clearSession: function () {} }; };

const api = require("../miniprogram/utils/api");

(async function () {
  await api.myStudents();
  assert(requests[0].url.endsWith("/api/v1/students/mine"));

  await api.studentAssignments(201);
  assert(requests[1].url.endsWith("/api/v1/assignments/mine?student_id=201"));

  await api.claimContract("JOIN-CODE", { student_id: 201, student_name: "学生甲" });
  assert.strictEqual(requests[2].data.student_id, 201);

  await api.submitAssignment([{ path: "sample.jpg" }], 501, "math", "grade7", 201);
  const multipart = new TextDecoder().decode(new Uint8Array(requests[3].data));
  assert(multipart.includes('name="student_id"\r\n\r\n201\r\n'));

  const auth = require("../miniprogram/utils/auth");
  let pageUser = null;
  const allowed = auth.guardRole({ setData: function (data) { pageUser = data.currentUser; } }, "student");
  assert.strictEqual(allowed, true, "authenticated teacher may enter family-student area");
  assert.strictEqual(pageUser.id, 9);
  assert.strictEqual(relaunches, 0, "family access does not redirect away");
  process.stdout.write("009BCD_MINIPROGRAM_CLIENT_PASS\n");
})().catch(function (error) {
  process.stderr.write(error.stack + "\n");
  process.exitCode = 1;
});
