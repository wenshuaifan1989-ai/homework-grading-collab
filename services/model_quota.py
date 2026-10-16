"""Fail-closed daily quota for paid external grading requests."""

from datetime import datetime, timezone
from secrets import token_hex
from zoneinfo import ZoneInfo

from sqlalchemy import func, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from config import settings
from models.model_usage import ModelCallAudit, ModelDailyUsage


SHANGHAI = ZoneInfo("Asia/Shanghai")


class ModelQuotaExceeded(RuntimeError):
    code = "MODEL_DAILY_LIMIT_REACHED"


def reserve_vision_call(db, task_id: str, provider: str, model_name: str) -> str:
    """Atomically reserve one call before any network request is made.

    A configured limit of zero disables paid calls. The atomic counter update
    makes the cap effective across multiple API/worker processes.
    """
    limit = max(0, int(settings.VISION_DAILY_REQUEST_LIMIT))
    if limit == 0:
        raise ModelQuotaExceeded("AI批改调用额度未启用；请先设置每日请求上限")

    usage_date = datetime.now(SHANGHAI).date()
    table = ModelDailyUsage.__table__
    dialect = db.bind.dialect.name
    if dialect == "mysql":
        statement = mysql_insert(table).values(usage_date=usage_date, request_count=0)
        db.execute(statement.on_duplicate_key_update(usage_date=usage_date))
    elif dialect == "sqlite":
        statement = sqlite_insert(table).values(usage_date=usage_date, request_count=0)
        db.execute(statement.on_conflict_do_nothing(index_elements=["usage_date"]))
    else:
        if db.query(ModelDailyUsage.usage_date).filter_by(usage_date=usage_date).first() is None:
            db.add(ModelDailyUsage(usage_date=usage_date, request_count=0))
            db.flush()

    updated = db.execute(
        update(ModelDailyUsage)
        .where(ModelDailyUsage.usage_date == usage_date, ModelDailyUsage.request_count < limit)
        .values(request_count=ModelDailyUsage.request_count + 1)
    )
    if updated.rowcount != 1:
        db.rollback()
        raise ModelQuotaExceeded("今日AI批改请求额度已用完")

    attempt_no = (db.query(func.max(ModelCallAudit.attempt_no))
        .filter(ModelCallAudit.task_id == task_id).scalar() or 0) + 1
    call_id = token_hex(12)
    db.add(ModelCallAudit(
        call_id=call_id,
        task_id=task_id,
        attempt_no=attempt_no,
        provider=provider,
        model_name=model_name,
        status="reserved",
    ))
    db.commit()
    return call_id


def finish_vision_call(db, call_id: str | None, status: str, error_code: str | None = None) -> None:
    if not call_id:
        return
    row = db.query(ModelCallAudit).filter_by(call_id=call_id).first()
    if row is None:
        return
    row.status = status
    row.error_code = error_code
    row.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
