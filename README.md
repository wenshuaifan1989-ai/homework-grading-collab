# 作业批改系统协同开发

作业批改系统包含 FastAPI 后端、Vue 管理与教师工作台、微信小程序客户端，以及 Celery 异步任务。

## 本地开发

1. 使用 Python 3.11 创建隔离环境，并安装 `requirements.txt`。
2. 将 `.env.example` 复制为本机 `.env`，只填写本机测试配置；不要提交 `.env`。
3. 按需启动本机数据库与 Redis，再运行 `uvicorn main:app --reload --port 8000`。
4. 在 `frontend/` 执行 `npm ci` 和 `npm run build`。
5. 在微信开发者工具中复制 `miniprogram/project.config.example.json` 为 `project.config.json`，仅在本机填写 AppID。

自动检查使用 SQLite/Mock 或本机测试替身，不连接生产数据库、不调用收费 API，也不部署。

## 目录

- `app/`、`clients/`、`models/`、`schemas/`、`services/`、`tasks/`、`utils/`：后端模块。
- `frontend/`：Vue 前端。
- `miniprogram/`：微信小程序代码。
- `scripts/`：共享数据库迁移和协同安全检查。
- `tests/`：共享自动化测试。

项目从公开参考仓库迁移。其 README 声明 MIT License；上游来源及许可证文件情况见 `UPSTREAM_NOTICES.md`。
