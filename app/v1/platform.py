from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.classroom import StudentRoster
from models.homework import HomeworkTask
from models.identity_relations import School, Student, StudentUserBinding
from models.user import User
from schemas.common import APIResponse
from schemas.identity_relations import (
    PlatformUserStatusRequest,
    RosterStudentCorrectionRequest,
    SchoolCreateRequest,
    StudentRelationCorrectionRequest,
)
from services.identity_relations import user_has_role, user_role_codes
from utils.database import get_db
from utils.deps import get_current_user


router = APIRouter(tags=["学校目录与平台管理"])


def _require_platform_admin(db: Session, user: User) -> None:
    if not user_has_role(db, user, "platform_admin"):
        raise HTTPException(status_code=403, detail="仅平台管理员可执行此操作")


def _school_payload(school: School) -> dict:
    return {
        "id": school.id,
        "official_name": school.official_name,
        "province": school.province,
        "city": school.city,
        "district": school.district,
        "stage": school.stage,
        "status": school.status,
        "is_custom": school.is_custom,
    }


@router.get("/schools", response_model=APIResponse)
def search_schools(
    q: str | None = Query(None, max_length=100),
    stage: str | None = Query(None, max_length=30),
    province: str | None = Query(None, max_length=50),
    city: str | None = Query(None, max_length=50),
    district: str | None = Query(None, max_length=50),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(School).filter(School.status.in_(["active", "pending_normalization"]))
    if q and q.strip():
        query = query.filter(School.official_name.ilike("%" + q.strip() + "%"))
    if stage:
        query = query.filter(School.stage == stage)
    if province:
        query = query.filter(School.province == province)
    if city:
        query = query.filter(School.city == city)
    if district:
        query = query.filter(School.district == district)
    rows = query.order_by(School.is_custom, School.official_name, School.id).limit(limit).all()
    return APIResponse(data=[_school_payload(row) for row in rows])


@router.post("/schools/custom", response_model=APIResponse)
def create_custom_school(
    request: SchoolCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user_has_role(db, user, "teacher") and not user_has_role(db, user, "platform_admin"):
        raise HTTPException(status_code=403, detail="仅教师或平台管理员可登记待规范学校")
    name = request.official_name.strip()
    existing = db.query(School).filter(
        School.official_name == name,
        School.province == request.province,
        School.city == request.city,
        School.district == request.district,
        School.stage == request.stage,
    ).first()
    if existing:
        return APIResponse(data=_school_payload(existing))
    school = School(
        official_name=name,
        province=request.province,
        city=request.city,
        district=request.district,
        stage=request.stage,
        status="pending_normalization",
        source="teacher_custom_entry",
        is_custom=True,
    )
    db.add(school)
    try:
        db.commit()
        db.refresh(school)
    except IntegrityError:
        db.rollback()
        existing = db.query(School).filter(
            School.official_name == name,
            School.province == request.province,
            School.city == request.city,
            School.district == request.district,
            School.stage == request.stage,
        ).first()
        if existing is None:
            raise HTTPException(status_code=409, detail="学校目录写入冲突")
        school = existing
    return APIResponse(data=_school_payload(school))


@router.get("/admin/users", response_model=APIResponse)
def admin_users(
    q: str | None = Query(None, max_length=100),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_platform_admin(db, user)
    query = db.query(User)
    if q and q.strip():
        pattern = "%" + q.strip() + "%"
        query = query.filter(or_(User.username.ilike(pattern), User.full_name.ilike(pattern), User.phone.ilike(pattern)))
    rows = query.order_by(User.id).offset(skip).limit(limit).all()
    return APIResponse(data=[{
        "id": row.id,
        "username": row.username,
        "full_name": row.full_name,
        "phone": row.phone,
        "role": row.role,
        "roles": sorted(user_role_codes(db, row)),
        "is_active": row.is_active,
    } for row in rows])


@router.get("/admin/students", response_model=APIResponse)
def admin_students(
    q: str | None = Query(None, max_length=100),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_platform_admin(db, user)
    query = db.query(Student)
    if q and q.strip():
        query = query.filter(Student.name.ilike("%" + q.strip() + "%"))
    rows = query.order_by(Student.id).offset(skip).limit(limit).all()
    return APIResponse(data=[{
        "id": row.id,
        "name": row.name,
        "status": row.status,
        "roster_count": db.query(StudentRoster.id).filter(StudentRoster.student_id == row.id).count(),
    } for row in rows])


@router.get("/admin/family-bindings", response_model=APIResponse)
def admin_family_bindings(
    student_id: int | None = Query(None, gt=0),
    user_id: int | None = Query(None, gt=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_platform_admin(db, user)
    query = db.query(StudentUserBinding, Student, User).join(
        Student, Student.id == StudentUserBinding.student_id
    ).join(User, User.id == StudentUserBinding.user_id)
    if student_id is not None:
        query = query.filter(StudentUserBinding.student_id == student_id)
    if user_id is not None:
        query = query.filter(StudentUserBinding.user_id == user_id)
    rows = query.order_by(Student.id, User.id).limit(500).all()
    return APIResponse(data=[{
        "student_id": student.id,
        "student_name": student.name,
        "user_id": account.id,
        "user_name": account.full_name or account.username,
        "relationship_type": binding.relationship_type,
        "relationship_label": binding.relationship_label,
        "status": binding.status,
    } for binding, student, account in rows])


@router.get("/admin/schools", response_model=APIResponse)
def admin_schools(
    q: str | None = Query(None, max_length=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_platform_admin(db, user)
    query = db.query(School)
    if q and q.strip():
        query = query.filter(School.official_name.ilike("%" + q.strip() + "%"))
    rows = query.order_by(School.id).limit(500).all()
    return APIResponse(data=[_school_payload(row) for row in rows])


@router.get("/admin/contacts", response_model=APIResponse)
def admin_contacts(
    q: str | None = Query(None, max_length=100),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_platform_admin(db, user)
    query = db.query(User)
    if q and q.strip():
        pattern = "%" + q.strip() + "%"
        query = query.filter(or_(User.phone.ilike(pattern), User.full_name.ilike(pattern)))
    rows = query.order_by(User.id).offset(skip).limit(limit).all()
    return APIResponse(data=[{
        "user_id": row.id,
        "name": row.full_name or row.username,
        "phone": row.phone,
        "email": row.email,
        "is_active": row.is_active,
    } for row in rows])


@router.get("/admin/homework", response_model=APIResponse)
def admin_homework(
    student_id: int | None = Query(None, gt=0),
    actor_user_id: int | None = Query(None, gt=0),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_platform_admin(db, user)
    query = db.query(HomeworkTask)
    if student_id is not None:
        query = query.filter(HomeworkTask.student_id == student_id)
    if actor_user_id is not None:
        query = query.filter(or_(HomeworkTask.actor_user_id == actor_user_id, HomeworkTask.user_id == actor_user_id))
    rows = query.order_by(HomeworkTask.created_at.desc(), HomeworkTask.id.desc()).offset(skip).limit(limit).all()
    return APIResponse(data=[{
        "task_id": row.task_id,
        "student_id": row.student_id,
        "actor_user_id": row.actor_user_id or row.user_id,
        "assignment_id": row.assignment_id,
        "class_id": row.class_id,
        "status": row.status,
        "total_score": float(row.total_score) if row.total_score is not None else None,
        "created_at": row.created_at,
    } for row in rows])


@router.post("/admin/users/{user_id}/status", response_model=APIResponse)
def admin_user_status(
    user_id: int,
    request: PlatformUserStatusRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_platform_admin(db, user)
    if user_id == user.id and not request.is_active:
        raise HTTPException(status_code=409, detail="不能禁用当前管理员账号")
    target = db.query(User).filter(User.id == user_id).with_for_update().first()
    if target is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target.is_active and not request.is_active and user_has_role(db, target, "platform_admin"):
        active_users = db.query(User).filter(User.is_active.is_(True)).all()
        active_admins = [account.id for account in active_users if user_has_role(db, account, "platform_admin")]
        if len(active_admins) <= 1:
            raise HTTPException(status_code=409, detail="不能禁用唯一的平台管理员")
    target.is_active = request.is_active
    db.commit()
    return APIResponse(data={"user_id": target.id, "is_active": target.is_active})


@router.post("/admin/students/{student_id}/family-bindings", response_model=APIResponse)
def admin_correct_family_binding(
    student_id: int,
    request: StudentRelationCorrectionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_platform_admin(db, user)
    if db.query(Student.id).filter(Student.id == student_id).first() is None:
        raise HTTPException(status_code=404, detail="学生不存在")
    if db.query(User.id).filter(User.id == request.user_id).first() is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    binding = db.query(StudentUserBinding).filter(
        StudentUserBinding.student_id == student_id,
        StudentUserBinding.user_id == request.user_id,
    ).first()
    if binding is None:
        binding = StudentUserBinding(
            student_id=student_id,
            user_id=request.user_id,
            relationship_type=request.relationship_type,
        )
        db.add(binding)
    binding.relationship_type = request.relationship_type
    binding.relationship_label = request.relationship_label
    binding.status = request.status
    db.commit()
    return APIResponse(data={"student_id": student_id, "user_id": request.user_id, "status": binding.status})


@router.post("/admin/classes/{class_id}/roster/{roster_id}/student", response_model=APIResponse)
def admin_correct_roster_student(
    class_id: int,
    roster_id: int,
    request: RosterStudentCorrectionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_platform_admin(db, user)
    roster = db.query(StudentRoster).filter(
        StudentRoster.id == roster_id,
        StudentRoster.class_id == class_id,
    ).with_for_update().first()
    if roster is None:
        raise HTTPException(status_code=404, detail="学生名册记录不存在")
    if request.student_id is not None:
        if db.query(Student.id).filter(Student.id == request.student_id).first() is None:
            raise HTTPException(status_code=404, detail="学生档案不存在")
        duplicate = db.query(StudentRoster.id).filter(
            StudentRoster.class_id == class_id,
            StudentRoster.student_id == request.student_id,
            StudentRoster.id != roster_id,
            StudentRoster.status == "active",
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="该学生已关联本班其他名册座位")
    roster.student_id = request.student_id
    db.commit()
    return APIResponse(data={"roster_id": roster.id, "student_id": roster.student_id})
