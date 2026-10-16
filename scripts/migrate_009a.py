"""Idempotent additive migration for 009A identity fields and UserRole."""

from sqlalchemy import String, inspect, select, text
from sqlalchemy.engine import make_url

from models.user import User
from models.user_role import UserRole
from config import settings
from utils.database import engine


EXPECTED_DATABASE = "homework_grading_dev"
USER_COLUMNS = {
    "wechat_openid": String(128),
    "wechat_unionid": String(128),
    "phone_source": String(20),
}


def migrate(bind=engine):
    inspector = inspect(bind)
    if not inspector.has_table("user"):
        raise RuntimeError("user 表不存在；009A 迁移不会创建或重建用户表")

    preparer = bind.dialect.identifier_preparer
    quoted_user = preparer.quote("user")
    with bind.begin() as connection:
        before_count = connection.execute(text("SELECT COUNT(*) FROM " + quoted_user)).scalar_one()
        existing_columns = {item["name"] for item in inspect(connection).get_columns("user")}
        if "phone" not in existing_columns:
            raise RuntimeError("user.phone 不存在，拒绝执行 phone_source 回填")
        for column_name, column_type in USER_COLUMNS.items():
            if column_name in existing_columns:
                continue
            quoted_column = preparer.quote(column_name)
            compiled_type = column_type.compile(dialect=bind.dialect)
            connection.execute(
                text(
                    f"ALTER TABLE {quoted_user} ADD COLUMN {quoted_column} {compiled_type} NULL"
                )
            )

        duplicate_openid = connection.execute(
            text(
                f"SELECT 1 FROM {quoted_user} WHERE {preparer.quote('wechat_openid')} "
                f"IS NOT NULL GROUP BY {preparer.quote('wechat_openid')} "
                "HAVING COUNT(*) > 1 LIMIT 1"
            )
        ).first()
        if duplicate_openid:
            raise RuntimeError("wechat_openid 存在重复值，拒绝创建唯一索引")

        UserRole.__table__.create(bind=connection, checkfirst=True)
        refreshed = inspect(connection)
        role_columns = {item["name"] for item in refreshed.get_columns("user_role")}
        required_role_columns = {"user_id", "role_code", "status", "created_at"}
        if not required_role_columns.issubset(role_columns):
            raise RuntimeError("现有 user_role 结构不兼容，拒绝继续迁移")
        unique_openid_exists = any(
            set(item.get("column_names") or []) == {"wechat_openid"}
            for item in refreshed.get_indexes("user")
            if item.get("unique")
        ) or any(
            set(item.get("column_names") or []) == {"wechat_openid"}
            for item in refreshed.get_unique_constraints("user")
        )
        if not unique_openid_exists:
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX "
                    + preparer.quote("uq_user_wechat_openid")
                    + f" ON {quoted_user} ({preparer.quote('wechat_openid')})"
                )
            )

        source_result = connection.execute(
            text(
                "UPDATE " + quoted_user + " SET " + preparer.quote("phone_source")
                + " = 'legacy' WHERE " + preparer.quote("phone") + " IS NOT NULL AND "
                + preparer.quote("phone_source") + " IS NULL"
            )
        )
        phone_sources_backfilled = max(source_result.rowcount, 0)

        users = connection.execute(
            select(User.id, User.role).order_by(User.id)
        ).all()
        existing_roles = {
            (user_id, role_code)
            for user_id, role_code in connection.execute(
                select(UserRole.user_id, UserRole.role_code)
            ).all()
        }
        inserted = 0
        for user_id, legacy_role in users:
            role_code = {"admin": "platform_admin", "teacher": "teacher"}.get(legacy_role)
            key = (user_id, role_code)
            if role_code and key not in existing_roles:
                connection.execute(
                    UserRole.__table__.insert().values(
                        user_id=user_id, role_code=role_code, status="active"
                    )
                )
                existing_roles.add(key)
                inserted += 1
        after_count = connection.execute(text("SELECT COUNT(*) FROM " + quoted_user)).scalar_one()
        if after_count != before_count:
            raise RuntimeError("009A 迁移期间 user 行数发生变化")

    return {
        "user_count_before": int(before_count),
        "user_count_after": int(after_count),
        "user_role_rows_inserted": inserted,
        "phone_sources_backfilled": phone_sources_backfilled,
        "user_columns": sorted(USER_COLUMNS),
    }


if __name__ == "__main__":
    target = make_url(settings.DATABASE_URL)
    if (
        not target.drivername.startswith("mysql")
        or target.database != EXPECTED_DATABASE
        or (target.host or "").lower() not in {"localhost", "127.0.0.1", "::1"}
    ):
        raise SystemExit(
            "REFUSED: 009A migration is restricted to local MySQL homework_grading_dev"
        )
    result = migrate()
    print("009A migration complete")
    for key, value in result.items():
        print(f"{key}={value}")
