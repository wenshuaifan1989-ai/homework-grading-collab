"""Additive, idempotent schema/data migration for 009BCD.

The executable entry point is restricted to the local development schema.
Tests may call migrate() with an isolated SQLite engine.
"""

from collections import defaultdict

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

from config import settings
from models.base import Base
from models.classroom import Class, StudentRoster
from models.homework import HomeworkTask
from models.identity_relations import (
    ClassTeacher,
    Contract,
    School,
    Student,
    StudentUserBinding,
)
from utils.database import engine


EXPECTED_DATABASE = "homework_grading_dev"
MIGRATION_ID = "009BCD_20261005_identity_relations"
NEW_TABLES = [
    Student.__table__,
    StudentUserBinding.__table__,
    ClassTeacher.__table__,
    Contract.__table__,
    School.__table__,
]
NEW_COLUMNS = {
    "student_roster": {
        "student_id": "BIGINT NULL",
        "disambiguation_note": "TEXT NULL",
    },
    "homework_task": {
        "student_id": "BIGINT NULL",
        "actor_user_id": "BIGINT NULL",
    },
    "classroom": {
        "school_id": "BIGINT NULL",
        "academic_year": "VARCHAR(20) NULL",
        "semester": "VARCHAR(20) NULL",
        "grade": "VARCHAR(20) NULL",
        "status": "VARCHAR(20) NOT NULL DEFAULT 'active'",
    },
}
FOREIGN_KEYS = (
    ("student_roster", "fk_student_roster_student", "student_id", "student", "id"),
    ("homework_task", "fk_homework_task_student", "student_id", "student", "id"),
    ("homework_task", "fk_homework_task_actor_user", "actor_user_id", "user", "id"),
    ("classroom", "fk_classroom_school", "school_id", "school", "id"),
)
INDEXES = (
    ("student_roster", "ix_student_roster_student_id", "student_id"),
    ("homework_task", "ix_homework_task_student_id", "student_id"),
    ("homework_task", "ix_homework_task_actor_user_id", "actor_user_id"),
    ("classroom", "ix_classroom_school_id", "school_id"),
)


def _count(connection, table: str) -> int:
    return int(connection.execute(text(f"SELECT COUNT(*) FROM `{table}`")).scalar_one())


def _ensure_columns(connection) -> list[str]:
    added = []
    dialect = connection.dialect.name
    if dialect not in {"mysql", "sqlite"}:
        raise RuntimeError(f"009BCD migration does not support dialect {dialect}")
    inspector = inspect(connection)
    for table, columns in NEW_COLUMNS.items():
        if not inspector.has_table(table):
            raise RuntimeError(f"REFUSED: required legacy table {table} is missing")
        existing = {column["name"] for column in inspector.get_columns(table)}
        for name, ddl in columns.items():
            if name in existing:
                continue
            connection.execute(text(f"ALTER TABLE `{table}` ADD COLUMN `{name}` {ddl}"))
            added.append(f"{table}.{name}")
        inspector = inspect(connection)
    return added


def _ensure_foreign_keys(connection) -> list[str]:
    if connection.dialect.name != "mysql":
        return []
    added = []
    inspector = inspect(connection)
    for table, name, column, ref_table, ref_column in FOREIGN_KEYS:
        if any(item.get("name") == name for item in inspector.get_foreign_keys(table)):
            continue
        orphan_count = connection.execute(text(
            f"SELECT COUNT(*) FROM `{table}` t LEFT JOIN `{ref_table}` r "
            f"ON r.`{ref_column}`=t.`{column}` "
            f"WHERE t.`{column}` IS NOT NULL AND r.`{ref_column}` IS NULL"
        )).scalar_one()
        if orphan_count:
            raise RuntimeError(
                f"REFUSED: {table}.{column} has {orphan_count} orphan references"
            )
        connection.execute(text(
            f"ALTER TABLE `{table}` ADD CONSTRAINT `{name}` "
            f"FOREIGN KEY (`{column}`) REFERENCES `{ref_table}` (`{ref_column}`)"
        ))
        added.append(name)
        inspector = inspect(connection)
    return added


def _ensure_indexes(connection) -> list[str]:
    added = []
    inspector = inspect(connection)
    for table, name, column in INDEXES:
        if any(item.get("name") == name for item in inspector.get_indexes(table)):
            continue
        connection.execute(text(f"CREATE INDEX `{name}` ON `{table}` (`{column}`)"))
        added.append(name)
        inspector = inspect(connection)
    return added


def _snapshot(connection) -> dict[str, int]:
    return {
        table: _count(connection, table)
        for table in (
            "user", "student", "student_user_binding", "student_roster",
            "homework_task", "classroom", "class_teacher", "contract", "school",
        )
        if inspect(connection).has_table(table)
    }


def _backfill(connection) -> dict[str, int]:
    quoted = connection.dialect.identifier_preparer.quote
    role_rows = connection.execute(text(
        f"SELECT u.id, u.role, r.id AS roster_id, r.student_name, r.student_id "
        f"FROM {quoted('user')} u JOIN {quoted('student_roster')} r "
        "ON r.bound_user_id=u.id ORDER BY u.id, r.id"
    )).mappings().all()
    roster_by_student_user: dict[int, list[dict]] = defaultdict(list)
    non_student_bound_rosters = 0
    for row in role_rows:
        if row["role"] == "student":
            roster_by_student_user[int(row["id"])].append(dict(row))
        elif row["student_id"] is None:
            non_student_bound_rosters += 1

    inserted_students = 0
    inserted_bindings = 0
    linked_rosters = 0
    ambiguous_users = 0
    for user_id, rows in roster_by_student_user.items():
        known_student_ids = {int(row["student_id"]) for row in rows if row["student_id"] is not None}
        binding_ids = {
            int(item[0])
            for item in connection.execute(text(
                "SELECT student_id FROM student_user_binding "
                "WHERE user_id=:uid AND relationship_type='self' AND status='active'"
            ), {"uid": user_id}).all()
        }
        known_student_ids |= binding_ids
        if len(known_student_ids) > 1:
            ambiguous_users += 1
            continue
        if known_student_ids:
            student_id = next(iter(known_student_ids))
        else:
            name = next((row["student_name"] for row in rows if row["student_name"]), "未命名学生")
            result = connection.execute(text(
                "INSERT INTO student (name, status) VALUES (:name, 'active')"
            ), {"name": name})
            student_id = int(result.lastrowid)
            inserted_students += 1

        for row in rows:
            if row["student_id"] is None:
                connection.execute(text(
                    "UPDATE student_roster SET student_id=:sid WHERE id=:rid AND student_id IS NULL"
                ), {"sid": student_id, "rid": row["roster_id"]})
                linked_rosters += 1
        existing_binding = connection.execute(text(
            "SELECT id FROM student_user_binding WHERE student_id=:sid AND user_id=:uid"
        ), {"sid": student_id, "uid": user_id}).first()
        if existing_binding is None:
            connection.execute(text(
                "INSERT INTO student_user_binding "
                "(student_id,user_id,relationship_type,status) "
                "VALUES (:sid,:uid,'self','active')"
            ), {"sid": student_id, "uid": user_id})
            inserted_bindings += 1

    unbound_rows = connection.execute(text(
        "SELECT id, student_name FROM student_roster "
        "WHERE bound_user_id IS NULL AND student_id IS NULL ORDER BY id"
    )).mappings().all()
    for row in unbound_rows:
        result = connection.execute(text(
            "INSERT INTO student (name, status) VALUES (:name, 'active')"
        ), {"name": row["student_name"] or "未命名学生"})
        connection.execute(text(
            "UPDATE student_roster SET student_id=:sid WHERE id=:rid AND student_id IS NULL"
        ), {"sid": int(result.lastrowid), "rid": row["id"]})
        inserted_students += 1
        linked_rosters += 1

    # Legacy task.user_id is the original acting account; preserve it and set
    # the new subject only when the user maps to exactly one Student.
    user_students: dict[int, set[int]] = defaultdict(set)
    for user_id, student_id in connection.execute(text(
        "SELECT DISTINCT r.bound_user_id, r.student_id FROM student_roster r "
        f"JOIN {quoted('user')} u ON u.id=r.bound_user_id "
        "WHERE u.role='student' AND r.student_id IS NOT NULL"
    )).all():
        user_students[int(user_id)].add(int(student_id))
    task_subjects_backfilled = 0
    ambiguous_task_users = 0
    task_rows = connection.execute(text(
        "SELECT id,user_id,student_id,actor_user_id FROM homework_task "
        "WHERE student_id IS NULL OR actor_user_id IS NULL"
    )).mappings().all()
    for task in task_rows:
        values = {}
        if task["actor_user_id"] is None:
            values["actor_user_id"] = task["user_id"]
        choices = user_students.get(int(task["user_id"]), set())
        if task["student_id"] is None and len(choices) == 1:
            values["student_id"] = next(iter(choices))
            task_subjects_backfilled += 1
        elif task["student_id"] is None and len(choices) > 1:
            ambiguous_task_users += 1
        if values:
            assignments = ", ".join(f"`{key}`=:{key}" for key in values)
            connection.execute(text(
                f"UPDATE homework_task SET {assignments} WHERE id=:id"
            ), {**values, "id": task["id"]})

    # Existing Class.teacher_id remains the compatibility source only until a
    # ClassTeacher owner exists. Never overwrite an already-established owner.
    inserted_owners = 0
    class_rows = connection.execute(text(
        "SELECT id,teacher_id,invite_code FROM classroom ORDER BY id"
    )).all()
    for class_id, teacher_id, _invite_code in class_rows:
        owners = connection.execute(text(
            "SELECT id FROM class_teacher WHERE class_id=:cid AND role='owner' AND status='active'"
        ), {"cid": class_id}).all()
        if len(owners) > 1:
            raise RuntimeError(f"REFUSED: class {class_id} has multiple active owners")
        if owners:
            continue
        existing = connection.execute(text(
            "SELECT id FROM class_teacher WHERE class_id=:cid AND teacher_user_id=:uid"
        ), {"cid": class_id, "uid": teacher_id}).first()
        if existing:
            connection.execute(text(
                "UPDATE class_teacher SET role='owner',status='active' WHERE id=:id"
            ), {"id": existing[0]})
        else:
            connection.execute(text(
                "INSERT INTO class_teacher "
                "(class_id,teacher_user_id,role,subject_codes_json,status) "
                "VALUES (:cid,:uid,'owner',NULL,'active')"
            ), {"cid": class_id, "uid": teacher_id})
        inserted_owners += 1

    seeded_student_contracts = 0
    for class_id, teacher_id, invite_code in class_rows:
        existing = connection.execute(text(
            "SELECT id,type,target_id FROM contract WHERE code=:code"
        ), {"code": invite_code}).first()
        if existing:
            if existing[1] != "STUDENT_CLASS_JOIN" or int(existing[2]) != int(class_id):
                raise RuntimeError(
                    f"REFUSED: legacy invite code for class {class_id} conflicts with Contract"
                )
            continue
        connection.execute(text(
            "INSERT INTO contract "
            "(type,code,target_id,creator_user_id,max_uses,used_count,status) "
            "VALUES ('STUDENT_CLASS_JOIN',:code,:class_id,:teacher_id,NULL,0,'active')"
        ), {"code": invite_code, "class_id": class_id, "teacher_id": teacher_id})
        seeded_student_contracts += 1

    return {
        "students_inserted": inserted_students,
        "bindings_inserted": inserted_bindings,
        "rosters_linked": linked_rosters,
        "ambiguous_student_users": ambiguous_users,
        "non_student_bound_rosters_left_nullable": non_student_bound_rosters,
        "homework_student_subjects_backfilled": task_subjects_backfilled,
        "ambiguous_homework_user_mappings": ambiguous_task_users,
        "class_owners_inserted": inserted_owners,
        "legacy_student_contracts_seeded": seeded_student_contracts,
    }


def migrate(bind=engine) -> dict:
    inspector = inspect(bind)
    required = {"user", "student_roster", "homework_task", "classroom"}
    missing = required - set(inspector.get_table_names())
    if missing:
        raise RuntimeError("REFUSED: required legacy tables missing: " + ",".join(sorted(missing)))

    Base.metadata.create_all(bind=bind, tables=NEW_TABLES, checkfirst=True)
    with bind.begin() as connection:
        added_columns = _ensure_columns(connection)
        added_foreign_keys = _ensure_foreign_keys(connection)
        added_indexes = _ensure_indexes(connection)

    with bind.connect() as connection:
        before = _snapshot(connection)
    with bind.begin() as connection:
        backfill = _backfill(connection)
    with bind.connect() as connection:
        after = _snapshot(connection)
    for table in ("user", "student_roster", "homework_task", "classroom"):
        if before[table] != after[table]:
            raise RuntimeError(f"009BCD migration unexpectedly changed legacy {table} row count")
    return {
        "migration_id": MIGRATION_ID,
        "counts_before": before,
        "counts_after": after,
        "columns_added": added_columns,
        "foreign_keys_added": added_foreign_keys,
        "indexes_added": added_indexes,
        **backfill,
    }


if __name__ == "__main__":
    url = make_url(settings.DATABASE_URL)
    if (
        not url.drivername.startswith("mysql")
        or url.database != EXPECTED_DATABASE
        or (url.host or "").lower() not in {"localhost", "127.0.0.1", "::1"}
    ):
        raise SystemExit(
            "REFUSED: 009BCD migration is restricted to local MySQL homework_grading_dev"
        )
    result = migrate(engine)
    for key, value in result.items():
        print(f"{key}={value}")
