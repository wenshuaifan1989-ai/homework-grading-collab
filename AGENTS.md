# Codex 项目规则

## 目标和边界

- 本仓库是双人协同开发用的源码基线；GitHub `wenshuaifan1989-ai/homework-grading-collab` 是跨电脑共享源码与评审的唯一位置，当前为公开仓库，任何人都能查看、克隆和派生。
- 不在提交中包含密钥、账号、真实学员资料、作业图片、数据库备份、运行日志、证据或本机配置。
- 不连接生产数据库、不调用收费服务、不部署或发布，除非任务明确授权并另行通过门禁。
- 原参考项目历史不属于本仓库历史；本仓库使用从 `develop` 开始的新 Git 历史。

## 开发流程

- 学生端独立开发时先读 `docs/collaboration/ROLE_OWNERSHIP.md` 的“自主开发、合并审核”约定：现有V2-001授权可直接执行，不再向负责人重复索要任务编号、验收标准或逐项开发许可；共享接口/模型的候选改动可在独立分支和隔离测试环境自主完成，审核集中在集成PR。

- `develop` 受 GitHub 分支保护：每项工作从最新 `develop` 建立短期分支：`feature/<任务编号>-<简短名称>` 或 `fix/<任务编号>-<简短名称>`。
- 开始前检查 `git status`，提交前检查差异、执行适用测试并运行 `python scripts/check_collab_safety.py`。
- 只能通过 Pull Request 合并到 `develop`；必须由另一位开发者批准，`python-tests` 与 `frontend-build` 均通过且分支为最新。最终合并仅由 `wenshuaifan1989-ai` 本人确认后执行；Codex不因检查全绿自动合并。独立分支推送和创建PR无需预先批准。现有保护与owner-only更新规则共同执行，不允许直接推送、强推、删除或绕过PR/CI。
- Codex Worktree 是本机隔离区，不是跨电脑同步机制；两台电脑通过 Git fetch、分支与 Pull Request 协作。
- 仓库公开意味着源码、提交、PR 和 Actions 日志可被公众查看；提交前必须再次检查公开内容，严禁放入秘密、真实学生资料或本机证据。

## 代码和测试

- 后端单元测试：`python -m pytest -q tests`。
- 前端构建：在 `frontend/` 执行 `npm ci`、`npm run build`。
- 小程序提交前执行 `python scripts/check_miniprogram.py`。
- 修改数据库/API/题目标识/批改规则等共享契约时，在PR中提供兼容性、迁移与回滚及负例测试；不把这些材料变成独立开发前的审批。
- 测试必须使用合成数据、SQLite/Mock 或临时文件；不得依赖真实学员信息或本机私有数据。
