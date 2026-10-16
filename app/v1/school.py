import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.classroom import Class, ClassMember, StudentRoster
from models.identity_relations import ClassTeacher, Student, StudentUserBinding
from models.user import User
from schemas.classroom import (
    AccountStatusRequest,
    PasswordResetRequest,
    StudentBindingOptionsRequest,
    StudentBindingRequest,
    StudentRosterBatchRequest,
    StudentRosterCreateRequest,
    TeacherCreateRequest,
)
from schemas.common import APIResponse
from utils.accounts import create_phone_user
from utils.database import get_db
from utils.deps import get_current_user
from utils.security import get_password_hash
from services.identity_relations import user_has_role

router = APIRouter(tags=["学校账号与学生名册"])


@router.get("/students/mine", response_model=APIResponse)
def list_my_students(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = (
        db.query(Student, StudentUserBinding)
        .join(StudentUserBinding, StudentUserBinding.student_id == Student.id)
        .filter(
            StudentUserBinding.user_id == user.id,
            StudentUserBinding.status == "active",
            Student.status == "active",
        )
        .order_by(Student.name, Student.id)
        .all()
    )
    payload = []
    for student, binding in rows:
        classes = (
            db.query(StudentRoster, Class)
            .join(Class, Class.id == StudentRoster.class_id)
            .filter(
                StudentRoster.student_id == student.id,
                StudentRoster.status.in_(["active", "pending_leave"]),
                Class.status == "active",
            )
            .order_by(Class.name, Class.id)
            .all()
        )
        payload.append({
            "student_id": student.id,
            "name": student.name,
            "relationship_type": binding.relationship_type,
            "relationship_label": binding.relationship_label,
            "status": student.status,
            "classes": [{
                "class_id": roster.class_id,
                "class_name": classroom.name,
                "status": roster.status,
            } for roster, classroom in classes],
        })
    return APIResponse(data=payload)


def _require_admin(db: Session, user: User) -> None:
    if not user_has_role(db, user, "platform_admin"):
        raise HTTPException(status_code=403, detail="仅管理员可执行此操作")


def _managed_class(
    db: Session, class_id: int, user: User, *, owner_only: bool = False
) -> Class:
    query = db.query(Class).filter(Class.id == class_id)
    if user_has_role(db, user, "platform_admin"):
        classroom = query.first()
        if classroom is None:
            raise HTTPException(status_code=404, detail="班级不存在")
        return classroom
    if user_has_role(db, user, "teacher"):
        classroom = query.first()
        membership = db.query(ClassTeacher).filter(
            ClassTeacher.class_id == class_id,
            ClassTeacher.teacher_user_id == user.id,
            ClassTeacher.status == "active",
        ).first()
        class_has_relations = db.query(ClassTeacher.id).filter(
            ClassTeacher.class_id == class_id
        ).first() is not None
        if classroom is None or (
            membership is None and (class_has_relations or classroom.teacher_id != user.id)
        ):
            raise HTTPException(status_code=404, detail="班级不存在")
        if owner_only and membership is not None and membership.role != "owner":
            raise HTTPException(status_code=403, detail="仅班级 owner 可维护名册")
        return classroom
    else:
        raise HTTPException(status_code=403, detail="仅教师或管理员可维护学生名册")


def _student_binding(db: Session, user_id: int):
    return (
        db.query(StudentRoster, Class)
        .join(Class, Class.id == StudentRoster.class_id)
        .filter(StudentRoster.bound_user_id == user_id)
        .first()
    )


def _roster_payload(roster: StudentRoster, bound_user: User | None = None) -> dict:
    return {
        "id": roster.id,
        "student_id": roster.student_id,
        "class_id": roster.class_id,
        "student_name": roster.student_name,
        "student_no": roster.student_no,
        "bound": roster.bound_user_id is not None,
        "bound_user_id": roster.bound_user_id,
        "bound_user_name": (
            (bound_user.full_name or bound_user.username) if bound_user else None
        ),
        "status": roster.status,
        "created_at": roster.created_at,
    }


def _roster_conflict(db: Session, class_id: int, student_name: str, student_no: str | None):
    if student_no is None:
        return False
    query = db.query(StudentRoster.id).filter(
        StudentRoster.class_id == class_id,
        StudentRoster.student_no == student_no,
    )
    return query.first() is not None


@router.get("/classes/{class_id}/roster", response_model=APIResponse)
def list_class_roster(
    class_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    classroom = _managed_class(db, class_id, user)
    rows = (
        db.query(StudentRoster, User)
        .outerjoin(User, User.id == StudentRoster.bound_user_id)
        .filter(StudentRoster.class_id == classroom.id, StudentRoster.status == "active")
        .order_by(StudentRoster.student_name, StudentRoster.student_no, StudentRoster.id)
        .all()
    )
    return APIResponse(data=[_roster_payload(roster, bound_user) for roster, bound_user in rows])


@router.post("/classes/{class_id}/roster", response_model=APIResponse)
def add_roster_student(
    class_id: int,
    request: StudentRosterCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    classroom = _managed_class(db, class_id, user, owner_only=True)
    student_name = request.student_name.strip()
    student_no = request.student_no.strip() if request.student_no else None
    if _roster_conflict(db, classroom.id, student_name, student_no):
        raise HTTPException(status_code=409, detail="该学生名册记录已存在")

    roster = StudentRoster(
        class_id=classroom.id,
        student_name=student_name,
        student_no=student_no,
        status="active",
    )
    db.add(roster)
    try:
        db.commit()
        db.refresh(roster)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="学号已在该班级名册中")
    return APIResponse(data=_roster_payload(roster))


@router.post("/classes/{class_id}/roster/batch", response_model=APIResponse)
def add_roster_students_batch(
    class_id: int,
    request: StudentRosterBatchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    classroom = _managed_class(db, class_id, user, owner_only=True)
    parsed: list[tuple[str, str | None]] = []
    seen: set[tuple[str, str | None]] = set()
    for line_number, raw_line in enumerate(request.lines.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in re.split(r"[,，\t]", line)]
        if len(parts) > 2 or not parts[0] or (len(parts) == 2 and not parts[1]):
            raise HTTPException(
                status_code=422,
                detail=f"第 {line_number} 行格式无效；请使用“姓名”或“姓名,学号”",
            )
        student_name = parts[0]
        student_no = parts[1] if len(parts) == 2 else None
        if len(student_name) > 100 or (student_no and len(student_no) > 50):
            raise HTTPException(status_code=422, detail=f"第 {line_number} 行字段过长")
        item = (student_name, student_no)
        if item not in seen:
            parsed.append(item)
            seen.add(item)
    if not parsed:
        raise HTTPException(status_code=422, detail="请至少录入一名学生")

    created = 0
    skipped = 0
    try:
        for student_name, student_no in parsed:
            if _roster_conflict(db, classroom.id, student_name, student_no):
                skipped += 1
                continue
            db.add(StudentRoster(
                class_id=classroom.id,
                student_name=student_name,
                student_no=student_no,
                status="active",
            ))
            created += 1
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="名册存在重复学号，批量录入未写入")
    return APIResponse(data={"created": created, "skipped": skipped})


@router.post(
    "/classes/{class_id}/roster/{roster_id}/unbind", response_model=APIResponse
)
def unbind_roster_student(
    class_id: int,
    roster_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    classroom = _managed_class(db, class_id, user, owner_only=True)
    roster = (
        db.query(StudentRoster)
        .filter(
            StudentRoster.id == roster_id,
            StudentRoster.class_id == classroom.id,
        )
        .with_for_update()
        .first()
    )
    if roster is None:
        raise HTTPException(status_code=404, detail="学生名册记录不存在")
    was_bound = roster.bound_user_id is not None
    previous_user_id = roster.bound_user_id
    roster.bound_user_id = None
    if was_bound and roster.student_id is not None:
        db.query(StudentUserBinding).filter(
            StudentUserBinding.student_id == roster.student_id,
            StudentUserBinding.user_id == previous_user_id,
            StudentUserBinding.relationship_type == "self",
            StudentUserBinding.status == "active",
        ).update({"status": "revoked"}, synchronize_session=False)
    db.commit()
    return APIResponse(data={"roster_id": roster.id, "unbound": was_bound})


@router.post("/students/binding-options", response_model=APIResponse)
def get_student_binding_options(
    request: StudentBindingOptionsRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != "student":
        raise HTTPException(status_code=403, detail="仅学生账号可绑定学生身份")
    invite_code = request.invite_code.strip().upper()
    classroom = db.query(Class).filter(Class.invite_code == invite_code).first()
    if classroom is None:
        raise HTTPException(status_code=404, detail="邀请码无效")
    roster_rows = []
    if request.student_name:
        student_name = request.student_name.strip()
        if student_name:
            roster_rows = (
                db.query(StudentRoster)
                .filter(
                    StudentRoster.class_id == classroom.id,
                    StudentRoster.student_name == student_name,
                    StudentRoster.bound_user_id.is_(None),
                    StudentRoster.status == "active",
                )
                .order_by(StudentRoster.id)
                .all()
            )
    return APIResponse(data={
        "class_id": classroom.id,
        "class_name": classroom.name,
        "invite_code": classroom.invite_code,
        "requires_name": not bool(request.student_name),
        "requires_disambiguation": len(roster_rows) > 1,
        "students": [_roster_payload(roster) for roster in roster_rows],
    })


@router.post("/students/bind", response_model=APIResponse)
def bind_student_identity(
    request: StudentBindingRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != "student":
        raise HTTPException(status_code=403, detail="仅学生账号可绑定学生身份")
    invite_code = request.invite_code.strip().upper()
    classroom = db.query(Class).filter(Class.invite_code == invite_code).first()
    if classroom is None:
        raise HTTPException(status_code=404, detail="邀请码无效")

    current = _student_binding(db, user.id)
    if current:
        current_roster, current_class = current
        if current_class.id != classroom.id:
            raise HTTPException(status_code=409, detail="邀请码与当前绑定班级不一致")
        if current_roster.id != request.roster_id:
            raise HTTPException(status_code=409, detail="一个学生账号只能绑定一个主班级")
        if current_roster.student_id is not None and db.query(StudentUserBinding.id).filter(
            StudentUserBinding.student_id == current_roster.student_id,
            StudentUserBinding.user_id == user.id,
            StudentUserBinding.status == "active",
        ).first() is None:
            db.add(StudentUserBinding(
                student_id=current_roster.student_id,
                user_id=user.id,
                relationship_type="self",
                status="active",
            ))
            db.commit()
        return APIResponse(data={
            "bound": True,
            "already_bound": True,
            "class_id": current_class.id,
            "class_name": current_class.name,
            "roster_id": current_roster.id,
            "student_id": current_roster.student_id,
            "student_name": current_roster.student_name,
            "student_no": current_roster.student_no,
        })

    roster = (
        db.query(StudentRoster)
        .filter(
            StudentRoster.id == request.roster_id,
            StudentRoster.class_id == classroom.id,
            StudentRoster.status == "active",
        )
        .with_for_update()
        .first()
    )
    if roster is None:
        raise HTTPException(status_code=404, detail="该学生不在邀请码对应的班级名册中")
    if roster.bound_user_id is not None:
        raise HTTPException(status_code=409, detail="该学生姓名已被其他账号绑定")

    student = db.query(Student).filter(Student.id == roster.student_id).first() if roster.student_id else None
    if student is None:
        student = Student(name=roster.student_name, status="active")
        db.add(student)
        db.flush()
        roster.student_id = student.id
    roster.bound_user_id = user.id
    binding = db.query(StudentUserBinding.id).filter(
        StudentUserBinding.student_id == student.id,
        StudentUserBinding.user_id == user.id,
    ).first()
    if binding is None:
        db.add(StudentUserBinding(
            student_id=student.id,
            user_id=user.id,
            relationship_type="self",
            status="active",
        ))
    membership = (
        db.query(ClassMember)
        .filter(ClassMember.class_id == classroom.id, ClassMember.student_id == user.id)
        .first()
    )
    if membership is None:
        db.add(ClassMember(class_id=classroom.id, student_id=user.id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="绑定冲突，请重新加载名册后重试")

    return APIResponse(data={
        "bound": True,
        "already_bound": False,
        "class_id": classroom.id,
        "class_name": classroom.name,
        "roster_id": roster.id,
        "student_id": student.id,
        "student_name": roster.student_name,
        "student_no": roster.student_no,
    })


@router.get("/students/binding", response_model=APIResponse)
def get_student_binding(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != "student":
        raise HTTPException(status_code=403, detail="仅学生账号可查看绑定信息")
    binding = _student_binding(db, user.id)
    if binding is None:
        return APIResponse(data={"is_bound": False})
    roster, classroom = binding
    return APIResponse(data={
        "is_bound": True,
        "class_id": classroom.id,
        "class_name": classroom.name,
        "roster_id": roster.id,
        "student_id": roster.student_id,
        "student_name": roster.student_name,
        "student_no": roster.student_no,
    })


@router.post("/admin/teachers", response_model=APIResponse)
def create_teacher(
    request: TeacherCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(db, user)
    if db.query(User.id).filter(User.phone == request.phone).first():
        raise HTTPException(status_code=409, detail="该手机号已注册")
    teacher = create_phone_user(
        db,
        phone=request.phone,
        password=request.password,
        role="teacher",
        full_name=request.full_name,
    )
    try:
        db.commit()
        db.refresh(teacher)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="手机号已被使用")
    return APIResponse(data={
        "id": teacher.id,
        "phone": teacher.phone,
        "full_name": teacher.full_name,
        "role": teacher.role,
        "is_active": teacher.is_active,
        "created_at": teacher.created_at,
    })


@router.get("/admin/teachers", response_model=APIResponse)
def list_teachers(
    q: str | None = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(db, user)
    teachers = [account for account in db.query(User).order_by(User.created_at.desc(), User.id.desc()).all()
                if user_has_role(db, account, "teacher")]
    if q and q.strip():
        needle = q.strip().lower()
        teachers = [account for account in teachers if needle in (account.full_name or "").lower()
                    or needle in (account.phone or "") or needle in account.username.lower()]
    teachers = teachers[max(skip, 0):max(skip, 0) + min(max(limit, 1), 100)]
    return APIResponse(data=[{
        "id": teacher.id,
        "phone": teacher.phone,
        "full_name": teacher.full_name,
        "role": teacher.role,
        "is_active": teacher.is_active,
        "class_count": db.query(ClassTeacher.class_id).filter(
            ClassTeacher.teacher_user_id == teacher.id,
            ClassTeacher.status == "active",
        ).distinct().count(),
        "is_active": teacher.is_active,
    } for teacher in teachers])


@router.post("/admin/teachers/{teacher_id}/status", response_model=APIResponse)
def update_teacher_status(
    teacher_id: int,
    request: AccountStatusRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(db, user)
    teacher = db.query(User).filter(User.id == teacher_id, User.role == "teacher").first()
    if teacher is None:
        raise HTTPException(status_code=404, detail="教师账号不存在")
    teacher.is_active = request.is_active
    db.commit()
    return APIResponse(data={"id": teacher.id, "is_active": teacher.is_active})


@router.post("/admin/teachers/{teacher_id}/password", response_model=APIResponse)
def reset_teacher_password(
    teacher_id: int,
    request: PasswordResetRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(db, user)
    teacher = db.query(User).filter(User.id == teacher_id, User.role == "teacher").first()
    if teacher is None:
        raise HTTPException(status_code=404, detail="教师账号不存在")
    teacher.hashed_password = get_password_hash(request.password)
    db.commit()
    return APIResponse(data={"id": teacher.id, "password_reset": True})


@router.get("/admin/classes", response_model=APIResponse)
def list_all_classes(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(db, user)
    rows = (
        db.query(Class, User)
        .join(User, User.id == Class.teacher_id)
        .order_by(Class.created_at.desc(), Class.id.desc())
        .all()
    )
    return APIResponse(data=[{
        "id": classroom.id,
        "name": classroom.name,
        "teacher_id": teacher.id,
        "teacher_name": teacher.full_name or teacher.username,
        "invite_code": classroom.invite_code,
        "school_id": classroom.school_id,
        "academic_year": classroom.academic_year,
        "semester": classroom.semester,
        "grade": classroom.grade,
        "status": classroom.status,
        "roster_count": db.query(StudentRoster.id)
        .filter(StudentRoster.class_id == classroom.id, StudentRoster.status == "active")
        .count(),
    } for classroom, teacher in rows])
