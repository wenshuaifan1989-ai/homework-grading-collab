# V2 responsibilities and review ownership

Status: owner-authorized working agreement. Student collaborator Write access is active; this does not prove two-device integration acceptance.

## 自主开发、合并审核

负责人已授权：santaozy123-hub在自己的clone、独立分支和隔离开发/测试环境完全自主推进学生Web及学生小程序。直接沿用现有V2-001及本仓库已明确的学生业务验收目标，不再要求负责人重复提供TASK_ID、整份验收标准、开工许可或逐项确认。自行拆分工作、实现界面、修复缺陷、测试、提交、同步最新develop、推送权属明确且无敏感内容的分支、创建/更新PR，均无需事前审批。

为完成学生端，可以自主实现或试验公共API、数据模型、鉴权适配、路由及共享组件的候选变更；写在自己的分支并只迁移隔离测试库，不需要先等负责人同意。记录兼容性、迁移/补偿及测试，在合入共同版本的PR中一次性交负责人审定。管理/教师/学生最终共用原系统及正式合同，不自行替换已部署接口或改共享/生产数据库；不覆盖其他人的工作树。

只有合并至共同版本develop时需要负责人wenshuaifan1989-ai确认。保留PR、非作者评审、CI与权限负例，最终由负责人本人操作合并或明确授权该次合并；Codex不根据全绿自动合并，同事也不代负责人点合并。仓库规则仅允许owner账号通过PR更新develop；不限制其他开发分支。

自主开发不授权泄露秘密/真实学生数据、公开来源许可不清的代码素材、收费调用、生产迁移或部署。来源已确认的原创改动可自行推送和提PR，不需要因全局LICENSE_PENDING暂停所有工作；具体来源不明部分留本地并列明问题，其余继续。只有真正无法安全继续的事项才提交具体阻断，不用重复索要任务文件替代开发。

学生端既定验收：身份/本人学生绑定、我的作业、冻结题号与必做/选做、1-9张一次提交一个HomeworkTask、结果/待复核、错题订正、越权负例；学生界面不显示L1/L2/L3。未验证的真实GUI、模型或设备能力保持PENDING。

| Area | Primary owner | Actual paths | Review boundary |
|---|---|---|---|
| Admin and teacher Web | wenshuaifan1989-ai | frontend/src/views/PlatformAdminView.vue, TeacherV2WorkspaceView.vue, TeacherWorkspaceView.vue, TeacherMistakesView.vue, KnownAssignmentsView.vue, LearningAdviceView.vue, AssignmentPlansView.vue | Another authorized developer approves the PR |
| Student Web | santaozy123-hub | frontend/src/views/StudentWorkspaceView.vue, StudentMistakesView.vue; frontend/src/api/student.ts | Owner reviews API, identity and submission compatibility |
| Student mini-program | santaozy123-hub | miniprogram/pages/student/ (bind, homework, detail, submit, result, mistakes) | No separate tracked components directory currently; shared auth/upload helpers require owner review |
| Public contracts, auth, database | wenshuaifan1989-ai (integration review) | app/v1/, schemas/, models/, services/, utils/; frontend/src/api/client.ts, frontend/src/stores/auth.ts; miniprogram/utils/ | Candidate branch and isolated-schema work is autonomous; owner reviews the final contract at integration |
| Shared shell and build | joint, owner reviews integration | frontend/src/components/AppLayout.vue, frontend/src/router/index.ts, frontend/src/styles/, .github/workflows/, requirements.txt | Autonomous candidate edits on separate branches; compatibility and conflicts reviewed at integration |

The collaborator's GitHub Write permission is repository-wide. These boundaries are review responsibilities, not directory-level access controls. CODEOWNERS.proposed is a suggestion, not an active server restriction.

Use separate clones/worktrees and short-lived feature branches. Fetch develop before starting. Do not overwrite another checkout's changes. Each PR states affected endpoints, compatibility window, tests, UI evidence and rollback. Keep the existing immutable publication and HOLD_REVIEW behavior.

PR #1 contains the CI prerequisite and collaboration rules. Its checks passing on a feature branch does not make develop green. The author cannot supply the required independent approval. The student's Write invitation is accepted; independent clone/push/review acceptance still needs actual evidence, not owner impersonation.

New upstream-derived business changes remain local while LICENSE_PENDING is unresolved. Do not add private papers, catalog exports, governance evidence, credentials or database snapshots to public Git.
