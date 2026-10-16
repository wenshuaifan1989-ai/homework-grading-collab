import os
import sys

# 添加项目路径到 sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from celery import Celery
from config import settings

celery_app = Celery(
    "homework_tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["tasks.homework_tasks"],
)

# 配置Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=settings.CELERY_TASK_TIMEOUT,
    worker_prefetch_multiplier=settings.CELERY_WORKER_PREFETCH_MULTIPLIER,
    task_track_started=True,
    worker_pool="solo",
)

# 路由配置
celery_app.conf.task_routes = {
    "tasks.homework_tasks.process_homework_task": {"queue": "homework"},
    "tasks.homework_tasks.process_analyze_task": {"queue": "homework"},
    "tasks.homework_tasks.process_grade_only_task": {"queue": "homework"},
}
