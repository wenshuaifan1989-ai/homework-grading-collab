import secrets
import string
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from models.classroom import Assignment, Class, ClassMember, StudentRoster, shanghai_today
from models.homework import HomeworkTask
from models.identity_relations import ClassTeacher, Contract, School, StudentUserBinding
from services.learning import student_assignment_variant_fields
from models.user import User
from schemas.classroom import (
    AssignmentCreateRequest,
    ClassCreateRequest,
    ClassJoinRequest,
)
from schemas.common import APIResponse
from services.task_service import task_service
from services.dashboard_service import (
    build_daily_dashboard,
    build_question_students,
    get_calendar_dates,
)
from utils.database import get_db
from utils.deps import get_current_user
from services.identity_relations import user_has_role


router = APIRouter(tags=["班级与教师作业"])
_INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _require_role(user: User, role: str, db: Session | None = None) -> None:
    allowed = user_has_role(db, user, role) if db is not None else user.role == role
    if not allowed:
        raise HTTPException(status_code=403, detail="无权执行此操作")


def _teacher_class(db: Session, class_id: int, teacher_id: int) -> Class:
    classroom = db.query(Class).filter(Class.id == class_id).first()
    membership = db.query(ClassTeacher.id).filter(
        ClassTeacher.class_id == class_id,
        ClassTeacher.teacher_user_id == teacher_id,
        ClassTeacher.status == "active",
    ).first()
    class_has_relations = db.query(ClassTeacher.id).filter(
        ClassTeacher.class_id == class_id
    ).first() is not None
    if classroom is not None and membership is None and (
        class_has_relations or classroom.teacher_id != teacher_id
    ):
        classroom = None
    if classroom is None:
        raise HTTPException(status_code=404, detail="班级不存在")
    return classroom


def _teacher_assignment(db: Session, assignment_id: int, teacher_id: int) -> Assignment:
    assignment = (
        db.query(Assignment)
        .filter(
            Assignment.id == assignment_id,
        )
        .first()
    )
    if assignment is None:
        raise HTTPException(status_code=404, detail="作业不存在")
    classroom = db.query(Class).filter(Class.id == assignment.class_id).first()
    membership = db.query(ClassTeacher).filter(
        ClassTeacher.class_id == assignment.class_id,
        ClassTeacher.teacher_user_id == teacher_id,
        ClassTeacher.status == "active",
    ).first()
    class_has_relations = db.query(ClassTeacher.id).filter(
        ClassTeacher.class_id == assignment.class_id
    ).first() is not None
    if classroom is None or (
        membership is None and (class_has_relations or classroom.teacher_id != teacher_id)
    ):
        raise HTTPException(status_code=404, detail="作业不存在")
    if membership and membership.subject_codes_json and assignment.subject not in membership.subject_codes_json:
        raise HTTPException(status_code=404, detail="作业不存在")
    return assignment


def _dashboard_class(db: Session, class_id: int, user: User) -> Class:
    """008 dashboard access: a teacher's own class or any class for admin."""
    if user_has_role(db, user, "platform_admin"):
        classroom = db.query(Class).filter(Class.id == class_id).first()
        if classroom is None:
            raise HTTPException(status_code=404, detail="班级不存在")
        return classroom
    if user_has_role(db, user, "teacher"):
        return _teacher_class(db, class_id, user.id)
    raise HTTPException(status_code=403, detail="学生无权访问班级教学仪表盘")


def _dashboard_assignment(db: Session, assignment_id: int, user: User) -> Assignment:
    if not user_has_role(db, user, 'platform_admin'):
        _require_role(user, 'teacher', db)
        return _teacher_assignment(db, assignment_id, user.id)
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if assignment is None:
        raise HTTPException(status_code=404, detail="作业不存在")
    _dashboard_class(db, assignment.class_id, user)
    return assignment


def _dashboard_subjects(db: Session, class_id: int, user: User):
    if user_has_role(db, user, 'platform_admin'):
        return None
    membership = db.query(ClassTeacher).filter_by(class_id=class_id,
        teacher_user_id=user.id, status='active').first()
    return membership.subject_codes_json or None if membership else None


def _parse_dashboard_date(value: Optional[str]) -> date:
    if not value:
        return shanghai_today()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="日期格式必须为 YYYY-MM-DD") from exc


def _assignment_payload(assignment: Assignment, class_name: str, task=None) -> dict:
    return {
        "id": assignment.id,
        "class_id": assignment.class_id,
        "class_name": class_name,
        "title": assignment.title,
        "description": assignment.description,
        "subject": assignment.subject,
        "grade": assignment.grade,
        "assignment_date": assignment.assignment_date,
        "due_at": assignment.due_at,
        "created_at": assignment.created_at,
        "status": assignment.status,
        "submitted": task is not None,
        "task_id": task.task_id if task else None,
        "task_status": task.status if task else None,
        "submitted_at": task.created_at if task else None,
    }


@router.post("/classes", response_model=APIResponse)
def create_class(
    request: ClassCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_role(user, "teacher", db)
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="班级名称不能为空")

    for _ in range(5):
        invite_code = "".join(secrets.choice(_INVITE_ALPHABET) for _ in range(8))
        if not db.query(Class.id).filter(Class.invite_code == invite_code).first():
            school = None
            if request.school_id is not None:
                school = db.query(School).filter(
                    School.id == request.school_id,
                    School.status.in_(["active", "pending_normalization"]),
                ).first()
                if school is None:
                    raise HTTPException(status_code=404, detail="学校不存在或不可选")
            classroom = Class(
                teacher_id=user.id,
                name=name,
                invite_code=invite_code,
                school_id=school.id if school else None,
                academic_year=request.academic_year,
                semester=request.semester,
                grade=request.grade,
            )
            db.add(classroom)
            try:
                db.flush()
                db.add(ClassTeacher(
                    class_id=classroom.id,
                    teacher_user_id=user.id,
                    role="owner",
                    subject_codes_json=None,
                    status="active",
                ))
                db.add(Contract(
                    type="STUDENT_CLASS_JOIN",
                    code=invite_code,
                    target_id=classroom.id,
                    creator_user_id=user.id,
                    max_uses=None,
                    used_count=0,
                    status="active",
                ))
                db.commit()
                db.refresh(classroom)
                return APIResponse(data={
                    "id": classroom.id,
                    "teacher_id": classroom.teacher_id,
                    "name": classroom.name,
                    "invite_code": classroom.invite_code,
                    "school_id": classroom.school_id,
                    "academic_year": classroom.academic_year,
                    "semester": classroom.semester,
                    "grade": classroom.grade,
                    "status": classroom.status,
                    "created_at": classroom.created_at,
                    "member_count": 0,
                })
            except IntegrityError:
                db.rollback()
    raise HTTPException(status_code=503, detail="暂时无法生成唯一邀请码")


@router.get("/classes/mine", response_model=APIResponse)
def list_my_classes(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_role(user, "teacher", db)
    classrooms = (
        db.query(Class)
        .outerjoin(
            ClassTeacher,
            and_(ClassTeacher.class_id == Class.id, ClassTeacher.teacher_user_id == user.id,
                 ClassTeacher.status == "active"),
        )
        .filter(or_(Class.teacher_id == user.id, ClassTeacher.id.is_not(None)))
        .distinct()
        .order_by(Class.created_at.desc(), Class.id.desc())
        .all()
    )
    return APIResponse(data=[
        {
            "id": classroom.id,
            "teacher_id": classroom.teacher_id,
            "name": classroom.name,
            "invite_code": classroom.invite_code,
            "school_id": classroom.school_id,
            "academic_year": classroom.academic_year,
            "semester": classroom.semester,
            "grade": classroom.grade,
            "status": classroom.status,
            "teacher_role": (
                db.query(ClassTeacher.role).filter(
                    ClassTeacher.class_id == classroom.id,
                    ClassTeacher.teacher_user_id == user.id,
                    ClassTeacher.status == "active",
                ).scalar()
                or ("owner" if classroom.teacher_id == user.id else "teacher")
            ),
            "created_at": classroom.created_at,
            "member_count": db.query(StudentRoster.id)
            .filter(
                StudentRoster.class_id == classroom.id,
                StudentRoster.status == "active",
            )
            .count(),
        }
        for classroom in classrooms
    ])


@router.post("/classes/join", response_model=APIResponse)
def join_class(
    request: ClassJoinRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_role(user, "student", db)
    raise HTTPException(
        status_code=409,
        detail="请使用班级邀请码完成学生身份绑定，不再支持直接加入班级",
    )


@router.post("/classes/{class_id}/assignments", response_model=APIResponse)
def create_assignment(
    class_id: int,
    request: AssignmentCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_role(user, "teacher", db)
    classroom = _teacher_class(db, class_id, user.id)
    membership = db.query(ClassTeacher).filter(
        ClassTeacher.class_id == classroom.id,
        ClassTeacher.teacher_user_id == user.id,
        ClassTeacher.status == "active",
    ).first()
    if membership and membership.subject_codes_json and request.subject not in membership.subject_codes_json:
        raise HTTPException(status_code=403, detail="当前教师无权发布该学科作业")
    title = request.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="作业标题不能为空")

    assignment = Assignment(
        class_id=classroom.id,
        teacher_id=user.id,
        title=title,
        description=request.description,
        subject=request.subject,
        grade=request.grade,
        assignment_date=request.assignment_date or shanghai_today(),
        due_at=request.due_at,
        status="published",
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return APIResponse(data=_assignment_payload(assignment, classroom.name))


@router.get("/classes/{class_id}/assignments", response_model=APIResponse)
def list_class_assignments(
    class_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """教师查看自己班级已发布的作业。"""
    _require_role(user, "teacher", db)
    classroom = _teacher_class(db, class_id, user.id)
    assignments = (
        db.query(Assignment)
        .filter(Assignment.class_id == classroom.id)
        .order_by(Assignment.created_at.desc(), Assignment.id.desc())
        .all()
    )
    payload = []
    for assignment in assignments:
        item = _assignment_payload(assignment, classroom.name)
        submitted_subjects = (
            db.query(HomeworkTask.student_id, HomeworkTask.user_id)
            .filter(
                HomeworkTask.assignment_id == assignment.id,
                HomeworkTask.class_id == classroom.id,
            )
            .all()
        )
        item["submission_count"] = len({
            ("student", int(student_id)) if student_id is not None else ("legacy_user", int(user_id))
            for student_id, user_id in submitted_subjects
        })
        payload.append(item)
    return APIResponse(data=payload)


@router.get("/assignments/mine", response_model=APIResponse)
def list_my_assignments(
    student_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    student_ids = [row[0] for row in db.query(StudentUserBinding.student_id).filter(
        StudentUserBinding.user_id == user.id,
        StudentUserBinding.status == "active",
    ).all()]
    if student_id is not None:
        if student_id not in student_ids:
            raise HTTPException(status_code=403, detail="当前账号无权查看该学生作业")
        student_ids = [student_id]
    roster_query = db.query(StudentRoster).filter(StudentRoster.status == "active")
    if student_ids:
        roster_query = roster_query.filter(
            or_(StudentRoster.student_id.in_(student_ids), StudentRoster.bound_user_id == user.id)
        )
    else:
        roster_query = roster_query.filter(StudentRoster.bound_user_id == user.id)
    roster_rows = roster_query.all()
    class_ids = sorted({row.class_id for row in roster_rows})
    if not class_ids:
        return APIResponse(data=[])

    assignments = (
        db.query(Assignment, Class.name)
        .join(Class, Class.id == Assignment.class_id)
        .filter(Assignment.class_id.in_(class_ids), Assignment.status == "published")
        .order_by(Assignment.created_at.desc(), Assignment.id.desc())
        .all()
    )
    payload = []
    from models.learning_advice import PracticeRecommendation
    from services.learning_advice import can_receive_practice
    practices = {p.assignment_id:p for p in db.query(PracticeRecommendation).filter(
        PracticeRecommendation.assignment_id.in_([a.id for a,_ in assignments])).all()}
    for assignment, class_name in assignments:
        for roster in roster_rows:
            if roster.class_id != assignment.class_id:
                continue
            if not can_receive_practice(practices.get(assignment.id), roster.student_id):
                continue
            task_query = db.query(HomeworkTask).filter(
                HomeworkTask.assignment_id == assignment.id,
                HomeworkTask.class_id == assignment.class_id,
            )
            if roster.student_id is not None:
                task_query = task_query.filter(or_(
                    HomeworkTask.student_id == roster.student_id,
                    and_(HomeworkTask.student_id.is_(None), HomeworkTask.user_id == user.id),
                ))
            elif roster.bound_user_id is not None:
                task_query = task_query.filter(
                    HomeworkTask.student_id.is_(None), HomeworkTask.user_id == user.id
                )
            else:
                continue
            task = task_query.order_by(
                HomeworkTask.created_at.desc(), HomeworkTask.id.desc()
            ).first()
            item = _assignment_payload(assignment, class_name, task)
            item.update({
                "student_id": roster.student_id,
                "student_name": roster.student_name,
                "roster_id": roster.id,
            })
            item.update(student_assignment_variant_fields(
                db,
                assignment,
                int(roster.student_id or 0),
                task.task_id if task else None,
            ))
            payload.append(item)
    return APIResponse(data=payload)


@router.get("/assignments/{assignment_id}/submissions", response_model=APIResponse)
def list_assignment_submissions(
    assignment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_role(user, "teacher", db)
    assignment = _teacher_assignment(db, assignment_id, user.id)
    students = (
        db.query(StudentRoster, User)
        .outerjoin(User, User.id == StudentRoster.bound_user_id)
        .filter(
            StudentRoster.class_id == assignment.class_id,
            StudentRoster.status == "active",
        )
        .order_by(StudentRoster.student_name, StudentRoster.id)
        .all()
    )
    tasks = (
        db.query(HomeworkTask)
        .filter(
            HomeworkTask.assignment_id == assignment.id,
            HomeworkTask.class_id == assignment.class_id,
        )
        .order_by(HomeworkTask.created_at.desc(), HomeworkTask.id.desc())
        .all()
    )
    latest_task = {}
    for task in tasks:
        key = ("student", task.student_id) if task.student_id is not None else ("user", task.user_id)
        latest_task.setdefault(key, task)

    payload = []
    for roster, _legacy_user in students:
        task = latest_task.get(("student", roster.student_id)) if roster.student_id is not None else None
        if task is None and roster.bound_user_id is not None:
            task = latest_task.get(("user", roster.bound_user_id))
        payload.append({
            "student_id": roster.bound_user_id,
            "student_entity_id": roster.student_id,
            "student_name": roster.student_name,
            "student_no": roster.student_no,
            "submitted": task is not None,
            "task_id": task.task_id if task else None,
            "task_status": task.status if task else None,
            "submitted_at": task.created_at if task else None,
            "total_score": float(task.total_score or 0) if task else None,
        })
    return APIResponse(data=payload)


@router.get(
    "/assignments/{assignment_id}/submissions/{student_id}/result",
    response_model=APIResponse,
)
def get_student_assignment_result(
    assignment_id: int,
    student_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_role(user, "teacher", db)
    assignment = _teacher_assignment(db, assignment_id, user.id)
    roster = (
        db.query(StudentRoster)
        .filter(
            StudentRoster.class_id == assignment.class_id,
            StudentRoster.bound_user_id == student_id,
            StudentRoster.status == "active",
        )
        .first()
    )
    if roster is None:
        raise HTTPException(status_code=404, detail="学生不属于该班级")

    task_query = db.query(HomeworkTask).filter(
        HomeworkTask.assignment_id == assignment.id,
        HomeworkTask.class_id == assignment.class_id,
    )
    task_query = task_query.filter(or_(
        HomeworkTask.student_id == roster.student_id if roster.student_id is not None else False,
        and_(HomeworkTask.student_id.is_(None), HomeworkTask.user_id == student_id),
    ))
    task = task_query.order_by(HomeworkTask.created_at.desc(), HomeworkTask.id.desc()).first()
    if task is None:
        raise HTTPException(status_code=404, detail="该学生尚未提交作业")
    result = task_service.get_grading_result(db, task.task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="批改结果不存在")
    return APIResponse(data={**result, "assignment_id": assignment.id})


@router.get(
    "/assignments/{assignment_id}/students/{student_entity_id}/result",
    response_model=APIResponse,
)
def get_student_entity_assignment_result(
    assignment_id: int,
    student_entity_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_role(user, "teacher", db)
    assignment = _teacher_assignment(db, assignment_id, user.id)
    roster = db.query(StudentRoster).filter(
        StudentRoster.class_id == assignment.class_id,
        StudentRoster.student_id == student_entity_id,
        StudentRoster.status == "active",
    ).first()
    if roster is None:
        raise HTTPException(status_code=404, detail="学生不属于该班级")
    query = db.query(HomeworkTask).filter(
        HomeworkTask.assignment_id == assignment.id,
        HomeworkTask.class_id == assignment.class_id,
    )
    if roster.bound_user_id is not None:
        query = query.filter(or_(
            HomeworkTask.student_id == student_entity_id,
            and_(HomeworkTask.student_id.is_(None), HomeworkTask.user_id == roster.bound_user_id),
        ))
    else:
        query = query.filter(HomeworkTask.student_id == student_entity_id)
    task = query.order_by(HomeworkTask.created_at.desc(), HomeworkTask.id.desc()).first()
    if task is None:
        raise HTTPException(status_code=404, detail="该学生尚未提交作业")
    result = task_service.get_grading_result(db, task.task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="批改结果不存在")
    return APIResponse(data={
        **result,
        "assignment_id": assignment.id,
        "student_id": student_entity_id,
        "actor_user_id": task.actor_user_id or task.user_id,
    })


@router.get("/classes/{class_id}/calendar", response_model=APIResponse)
def get_class_calendar(
    class_id: int,
    month: Optional[str] = Query(None, description="月份，格式 YYYY-MM"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """008: return assignment markers for one month without exposing other classes."""
    classroom = _dashboard_class(db, class_id, user)
    month_value = month or shanghai_today().strftime("%Y-%m")
    try:
        dates = get_calendar_dates(db, classroom.id, month_value, _dashboard_subjects(db, class_id, user))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="月份格式必须为 YYYY-MM") from exc
    return APIResponse(data={"month": month_value, "dates": dates})


@router.get("/classes/{class_id}/daily-dashboard", response_model=APIResponse)
def get_class_daily_dashboard(
    class_id: int,
    date: Optional[str] = Query(None, description="教学日期，格式 YYYY-MM-DD"),
    assignment_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """008: class daily teaching view with latest-submission and question counts."""
    classroom = _dashboard_class(db, class_id, user)
    selected_date = _parse_dashboard_date(date)
    if assignment_id is not None:
        assignment = _dashboard_assignment(db, assignment_id, user)
        if assignment.class_id != classroom.id or assignment.assignment_date != selected_date:
            raise HTTPException(status_code=404, detail="该日期没有此班级作业")
    payload = build_daily_dashboard(
        db, classroom, selected_date, assignment_id=assignment_id,
        allowed_subjects=_dashboard_subjects(db, class_id, user)
    )
    return APIResponse(data=payload)


@router.get("/assignments/{assignment_id}/questions/{question_key}/students", response_model=APIResponse)
def get_question_students(
    assignment_id: int,
    question_key: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """008: split one question into correct/wrong/unrecognized students."""
    assignment = _dashboard_assignment(db, assignment_id, user)
    payload = build_question_students(db, assignment, question_key)
    if payload is None:
        raise HTTPException(status_code=404, detail="题目不存在或题号无法标准化")
    return APIResponse(data=payload)
