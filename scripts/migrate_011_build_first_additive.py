"""Add 011 retry-safety tables without altering existing business tables."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings
from models.base import Base
from models.model_usage import ModelCallAudit, ModelDailyUsage
from models.submission import HomeworkSubmissionKey
from utils.database import engine


NEW_TABLES = (
    ModelDailyUsage.__table__,
    ModelCallAudit.__table__,
    HomeworkSubmissionKey.__table__,
)
PROTECTED_TABLES = (
    "user", "student", "student_user_binding", "classroom", "assignment",
    "homework_task", "homework_image", "grading_result",
)


def migrate(target_engine: Engine) -> dict:
    inspector = inspect(target_engine)
    with target_engine.connect() as connection:
        before = {
            table: connection.execute(text(f"SELECT COUNT(*) FROM `{table}`")).scalar_one()
            for table in PROTECTED_TABLES if inspector.has_table(table)
        }
    Base.metadata.create_all(bind=target_engine, tables=list(NEW_TABLES), checkfirst=True)
    after_inspector = inspect(target_engine)
    with target_engine.connect() as connection:
        after = {
            table: connection.execute(text(f"SELECT COUNT(*) FROM `{table}`")).scalar_one()
            for table in before
        }
    if before != after:
        raise RuntimeError("Protected business row counts changed during retry-safety migration")
    return {
        "migration": "011_build_first_retry_safety_v1",
        "tables_present": [table.name for table in NEW_TABLES if after_inspector.has_table(table.name)],
        "protected_rows_unchanged": before == after,
        "protected_rows_before": before,
        "protected_rows_after": after,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-local-demo", action="store_true")
    args = parser.parse_args()
    if not args.target_local_demo:
        parser.error("pass --target-local-demo; this migration is scoped to the isolated local DB")
    url = make_url(settings.DATABASE_URL)
    if url.host not in {"127.0.0.1", "localhost"} or url.database != "homework_grading_local":
        parser.error("refusing non-loopback or non-homework_grading_local database target")
    print(json.dumps(migrate(engine), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
