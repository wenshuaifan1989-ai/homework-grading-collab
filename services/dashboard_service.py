"""Small, deterministic aggregation helpers for the G5 class dashboard."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime
from typing import Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from models.classroom import Assignment, Class, StudentRoster
from models.homework import GradingResult, HomeworkTask
from models.identity_relations import StudentUserBinding


_STATUS_LABELS = {
    "unbound": "未绑定",
    "unsubmitted": "未提交",
    "grading": "批改中",
    "failed": "批改失败",
    "completed": "已完成",
    "waiting_review": "待教师复核",
}


def normalize_question_no(value: object) -> Optional[str]:
    """Normalize only the safe V0.1 forms: 1, 01 and 第1题."""
    if value is None:
        return None
    raw = re.sub(r"\s+", "", str(value).strip().lower())
    if raw.startswith("第") and raw.endswith("题"):
        raw = raw[1:-1]
    if not re.fullmatch(r"\d+", raw):
        return None
    return str(int(raw))


def _question_sort_key(key: str) -> tuple[int, object]:
    return (0, int(key)) if key.isdigit() else (1, key)


def _bucket(result: Optional[str]) -> str:
    value = (result or "").strip().lower()
    if value in {"correct", "right", "正确"}:
        return "correct"
    if value in {"wrong", "incorrect", "error", "partial", "部分正确", "错误"}:
        return "wrong"
    return "unrecognized"


def _month_bounds(month: str) -> tuple[date, date]:
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise ValueError("invalid month")
    first = date.fromisoformat(month + "-01")
    if first.month == 12:
        next_month = date(first.year + 1, 1, 1)
    else:
        next_month = date(first.year, first.month + 1, 1)
    return first, next_month


def get_calendar_dates(db: Session, class_id: int, month: str, allowed_subjects=None) -> list[dict]:
    first, next_month = _month_bounds(month)
    rows = (
        db.query(Assignment)
        .filter(
            Assignment.class_id == class_id,
            Assignment.status == "published",
            Assignment.assignment_date >= first,
            Assignment.assignment_date < next_month,
        )
        .order_by(Assignment.assignment_date, Assignment.id)
        .all()
    )
    if allowed_subjects is not None:
        rows = [row for row in rows if row.subject in allowed_subjects]
    grouped: dict[date, list[int]] = defaultdict(list)
    for row in rows:
        grouped[row.assignment_date].append(row.id)
    return [
        {
            "date": day.isoformat(),
            "assignment_count": len(ids),
            "assignment_ids": ids,
        }
        for day, ids in sorted(grouped.items())
    ]


def _roster_key(roster: StudentRoster) -> tuple[str, int] | None:
    if roster.student_id is not None:
        return ("student", int(roster.student_id))
    if roster.bound_user_id is not None:
        return ("user", int(roster.bound_user_id))
    return None


def _task_key(task: HomeworkTask) -> tuple[str, int]:
    if task.student_id is not None:
        return ("student", int(task.student_id))
    return ("user", int(task.user_id))


def _task_for_roster(
    latest: dict[tuple[str, int], HomeworkTask], roster: StudentRoster
) -> Optional[HomeworkTask]:
    if roster.student_id is not None:
        task = latest.get(("student", int(roster.student_id)))
        if task is not None:
            return task
    if roster.bound_user_id is not None:
        return latest.get(("user", int(roster.bound_user_id)))
    return None


def _latest_tasks(
    db: Session, assignment: Assignment, roster_rows: list[StudentRoster]
) -> dict[tuple[str, int], HomeworkTask]:
    student_ids = {row.student_id for row in roster_rows if row.student_id is not None}
    bound_ids = {row.bound_user_id for row in roster_rows if row.bound_user_id is not None}
    clauses = []
    if student_ids:
        clauses.append(HomeworkTask.student_id.in_(student_ids))
    if bound_ids:
        clauses.append(and_(HomeworkTask.student_id.is_(None), HomeworkTask.user_id.in_(bound_ids)))
    if not clauses:
        return {}
    rows = (
        db.query(HomeworkTask)
        .filter(
            HomeworkTask.assignment_id == assignment.id,
            HomeworkTask.class_id == assignment.class_id,
            or_(*clauses),
        )
        .order_by(HomeworkTask.created_at.desc(), HomeworkTask.id.desc())
        .all()
    )
    latest: dict[tuple[str, int], HomeworkTask] = {}
    for row in rows:
        latest.setdefault(_task_key(row), row)
    return latest


def _student_status(roster: StudentRoster, task: Optional[HomeworkTask], is_bound: bool) -> str:
    if not is_bound:
        return "unbound"
    if task is None:
        return "unsubmitted"
    if task.status == "SUCCESS":
        return "completed"
    if task.status in {"WAIT_REVIEW", "UNKNOWN_LAYOUT", "REVIEW_REQUIRED"}:
        return "waiting_review"
    if task.status in {"PENDING", "PROCESSING", "GRADING"}:
        return "grading"
    return "failed"


def _student_rows(
    roster_rows: list[StudentRoster],
    latest: dict[tuple[str, int], HomeworkTask],
    bound_student_ids: set[int],
) -> list[dict]:
    result = []
    for roster in sorted(roster_rows, key=lambda row: (row.student_name, row.id)):
        task = _task_for_roster(latest, roster)
        is_bound = roster.bound_user_id is not None or (
            roster.student_id is not None and roster.student_id in bound_student_ids
        )
        status = _student_status(roster, task, is_bound)
        result.append(
            {
                "roster_id": roster.id,
                "student_id": roster.student_id,
                "student_name": roster.student_name,
                "student_no": roster.student_no,
                "bind_status": "bound" if is_bound else "unbound",
                "user_id": roster.bound_user_id,
                "submission_status": status,
                "submission_status_label": _STATUS_LABELS[status],
                "task_id": task.task_id if task else None,
                "task_status": task.status if task else None,
                "score": float(task.total_score) if task and task.status == "SUCCESS" and task.total_score is not None else None,
            }
        )
    return result


def _question_details(
    db: Session,
    latest: dict[tuple[str, int], HomeworkTask],
    roster_rows: list[StudentRoster],
) -> tuple[list[dict], dict[tuple[tuple[str, int], str], tuple[str, Optional[str]]]]:
    success_tasks = [task for task in latest.values() if task.status == "SUCCESS"]
    task_ids = [task.task_id for task in success_tasks]
    rows = (
        db.query(GradingResult)
        .filter(GradingResult.task_id.in_(task_ids))
        .order_by(GradingResult.task_id, GradingResult.id)
        .all()
        if task_ids
        else []
    )
    grouped: dict[str, dict[str, list[GradingResult]]] = defaultdict(lambda: defaultdict(list))
    question_display: dict[str, str] = {}
    for row in rows:
        key = normalize_question_no(row.question_no)
        if key is None:
            continue
        grouped[row.task_id][key].append(row)
        question_display.setdefault(key, key)

    keys = sorted(
        {key for task_map in grouped.values() for key in task_map}, key=_question_sort_key
    )
    per_student: dict[tuple[tuple[str, int], str], tuple[str, Optional[str]]] = {}
    stats = []
    roster_by_key = {
        key: row for row in roster_rows if (key := _roster_key(row)) is not None
    }
    for key in keys:
        counts = {"correct": 0, "wrong": 0, "unrecognized": 0}
        for student_key, task in latest.items():
            if student_key not in roster_by_key or task.status != "SUCCESS":
                continue
            entries = grouped.get(task.task_id, {}).get(key, [])
            bucket = _bucket(entries[0].result) if len(entries) == 1 else "unrecognized"
            counts[bucket] += 1
            per_student[(student_key, key)] = (bucket, task.task_id)
        stats.append(
            {
                "question_key": key,
                "question_no": question_display[key],
                "correct_count": counts["correct"],
                "wrong_count": counts["wrong"],
                "unrecognized_count": counts["unrecognized"],
            }
        )
    return stats, per_student


def build_daily_dashboard(
    db: Session,
    classroom: Class,
    selected_date: date,
    assignment_id: Optional[int] = None,
    allowed_subjects=None,
) -> dict:
    roster_rows = (
        db.query(StudentRoster)
        .filter(StudentRoster.class_id == classroom.id, StudentRoster.status == "active")
        .all()
    )
    roster_student_ids = {row.student_id for row in roster_rows if row.student_id is not None}
    bound_student_ids = {
        int(row[0])
        for row in db.query(StudentUserBinding.student_id).filter(
            StudentUserBinding.student_id.in_(roster_student_ids),
            StudentUserBinding.status == "active",
        ).distinct().all()
    } if roster_student_ids else set()
    assignments = (
        db.query(Assignment)
        .filter(
            Assignment.class_id == classroom.id,
            Assignment.status == "published",
            Assignment.assignment_date == selected_date,
        )
        .order_by(Assignment.created_at, Assignment.id)
        .all()
    )
    if allowed_subjects is not None:
        assignments = [row for row in assignments if row.subject in allowed_subjects]
    assignment_ids = {row.id for row in assignments}
    if assignment_id is not None and assignment_id not in assignment_ids:
        raise ValueError("assignment is not in selected date")
    selected = next(
        (row for row in assignments if row.id == assignment_id), assignments[0] if assignments else None
    )
    assignment_payloads = []
    for assignment in assignments:
        latest = _latest_tasks(db, assignment, roster_rows)
        statuses = [
            _student_status(
                row,
                _task_for_roster(latest, row),
                row.bound_user_id is not None or (
                    row.student_id is not None and row.student_id in bound_student_ids
                ),
            )
            for row in roster_rows
        ]
        bound_statuses = [
            status for status, row in zip(statuses, roster_rows)
            if row.bound_user_id is not None or (
                row.student_id is not None and row.student_id in bound_student_ids
            )
        ]
        assignment_payloads.append(
            {
                "id": assignment.id,
                "title": assignment.title,
                "description": assignment.description,
                "subject": assignment.subject,
                "grade": assignment.grade,
                "assignment_date": assignment.assignment_date,
                "due_at": assignment.due_at,
                "submitted_count": sum(status != "unsubmitted" and status != "unbound" for status in statuses),
                "unsubmitted_count": bound_statuses.count("unsubmitted"),
                "grading_count": bound_statuses.count("grading"),
                "waiting_review_count": bound_statuses.count("waiting_review"),
                "completed_count": bound_statuses.count("completed"),
                "failed_count": bound_statuses.count("failed"),
            }
        )
    selected_latest = _latest_tasks(db, selected, roster_rows) if selected else {}
    question_stats, _ = _question_details(db, selected_latest, roster_rows) if selected else ([], {})
    return {
        "date": selected_date.isoformat(),
        "class": {
            "class_id": classroom.id,
            "class_name": classroom.name,
            "roster_total": len(roster_rows),
            "bound_count": sum(
                row.bound_user_id is not None or (
                    row.student_id is not None and row.student_id in bound_student_ids
                ) for row in roster_rows
            ),
            "unbound_count": sum(
                row.bound_user_id is None and (
                    row.student_id is None or row.student_id not in bound_student_ids
                ) for row in roster_rows
            ),
        },
        "selected_assignment_id": selected.id if selected else None,
        "assignments": assignment_payloads,
        "question_stats": question_stats,
        "students": _student_rows(roster_rows, selected_latest, bound_student_ids),
    }


def build_question_students(
    db: Session, assignment: Assignment, question_key: str
) -> Optional[dict]:
    roster_rows = (
        db.query(StudentRoster)
        .filter(StudentRoster.class_id == assignment.class_id, StudentRoster.status == "active")
        .all()
    )
    latest = _latest_tasks(db, assignment, roster_rows)
    stats, per_student = _question_details(db, latest, roster_rows)
    normalized = normalize_question_no(question_key)
    if normalized is None or not any(row["question_key"] == normalized for row in stats):
        return None
    selected_stat = next(row for row in stats if row["question_key"] == normalized)
    roster_by_key = {
        key: row for row in roster_rows if (key := _roster_key(row)) is not None
    }
    groups = {"correct": [], "wrong": [], "unrecognized": []}
    for (student_key, key), (bucket, task_id) in per_student.items():
        if key != normalized:
            continue
        roster = roster_by_key[student_key]
        groups[bucket].append(
            {
                "user_id": roster.bound_user_id,
                "student_id": roster.student_id,
                "roster_id": roster.id,
                "student_name": roster.student_name,
                "student_no": roster.student_no,
                "task_id": task_id,
            }
        )
    for values in groups.values():
        values.sort(key=lambda item: (item["student_name"], item["roster_id"]))
    return {
        "question_key": normalized,
        "question_no": selected_stat["question_no"],
        "correct_count": len(groups["correct"]),
        "wrong_count": len(groups["wrong"]),
        "unrecognized_count": len(groups["unrecognized"]),
        "correct_students": groups["correct"],
        "wrong_students": groups["wrong"],
        "unrecognized_students": groups["unrecognized"],
    }
