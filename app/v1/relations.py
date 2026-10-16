import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.classroom import Class, ClassMember, StudentRoster
from models.identity_relations import ClassTeacher, Contract, Student, StudentUserBinding
from models.user import User
from schemas.common import APIResponse
from schemas.identity_relations import (
    ClassStatusRequest,
    ContractClaimRequest,
    ContractCreateRequest,
    OwnerTransferRequest,
    RelationshipReviewRequest,
    StudentLeaveReviewRequest,
)
from services.identity_relations import active_student_ids, user_can_access_student, user_has_role
from utils.database import get_db
from utils.deps import get_current_user


router = APIRouter(tags=["身份关系与班级协同"])
RELATIONSHIP_TYPES = {
    "self", "father", "mother", "paternal_grandfather", "paternal_grandmother",
    "maternal_grandfather", "maternal_grandmother", "guardian", "other",
}


def _class_role(db: Session, class_id: int, user_id: int) -> ClassTeacher | None:
    return db.query(ClassTeacher).filter(
        ClassTeacher.class_id == class_id,
        ClassTeacher.teacher_user_id == user_id,
        ClassTeacher.status == "active",
    ).first()


def _classroom(db: Session, class_id: int) -> Class:
    classroom = db.query(Class).filter(Class.id == class_id).first()
    if classroom is None:
        raise HTTPException(status_code=404, detail="班级不存在")
    return classroom


def _require_class_teacher(db: Session, class_id: int, user: User) -> tuple[Class, ClassTeacher]:
    classroom = _classroom(db, class_id)
    if classroom.status != "active":
        raise HTTPException(status_code=409, detail="班级已归档或终止")
    membership = _class_role(db, class_id, user.id)
    if membership is None:
        raise HTTPException(status_code=404, detail="班级不存在")
    if not user_has_role(db, user, "teacher"):
        raise HTTPException(status_code=403, detail="仅教师可执行此操作")
    return classroom, membership


def _require_owner(db: Session, class_id: int, user: User) -> tuple[Class, ClassTeacher]:
    classroom, membership = _require_class_teacher(db, class_id, user)
    if membership.role != "owner":
        raise HTTPException(status_code=403, detail="仅班级 owner 可执行此操作")
    return classroom, membership


def _new_contract_code(db: Session) -> str:
    for _ in range(8):
        code = secrets.token_urlsafe(9)[:12]
        if db.query(Contract.id).filter(Contract.code == code).first() is None:
            return code
    raise HTTPException(status_code=503, detail="暂时无法生成唯一关系码")


def _contract_payload(contract: Contract) -> dict:
    return {
        "id": contract.id,
        "type": contract.type,
        "code": contract.code,
        "target_id": contract.target_id,
        "expires_at": contract.expires_at,
        "max_uses": contract.max_uses,
        "used_count": contract.used_count,
        "status": contract.status,
    }


def _create_contract(
    db: Session,
    *,
    contract_type: str,
    target_id: int,
    creator_id: int,
    expires_at: datetime | None = None,
    max_uses: int | None = None,
) -> Contract:
    db.query(Contract).filter(
        Contract.type == contract_type,
        Contract.target_id == target_id,
        Contract.status == "active",
    ).update({"status": "revoked"}, synchronize_session=False)
    contract = Contract(
        type=contract_type,
        code=_new_contract_code(db),
        target_id=target_id,
        creator_user_id=creator_id,
        expires_at=expires_at,
        max_uses=max_uses,
        used_count=0,
        status="active",
    )
    db.add(contract)
    db.flush()
    return contract


def _load_active_contract(db: Session, code: str) -> Contract:
    contract = db.query(Contract).filter(Contract.code == code).with_for_update().first()
    if contract is None:
        raise HTTPException(status_code=404, detail="关系码无效")
    if contract.status != "active":
        raise HTTPException(status_code=410, detail="关系码已失效")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expires_at = contract.expires_at
    if expires_at is not None:
        if expires_at.tzinfo is not None:
            expires_at = expires_at.astimezone(timezone.utc).replace(tzinfo=None)
        if expires_at <= now:
            contract.status = "expired"
            db.commit()
            raise HTTPException(status_code=410, detail="关系码已过期")
    if contract.max_uses is not None and contract.used_count >= contract.max_uses:
        contract.status = "exhausted"
        db.commit()
        raise HTTPException(status_code=410, detail="关系码使用次数已用完")
    return contract


def _consume(contract: Contract) -> None:
    contract.used_count += 1
    if contract.max_uses is not None and contract.used_count >= contract.max_uses:
        contract.status = "exhausted"


@router.post("/classes/{class_id}/contracts", response_model=APIResponse)
def create_class_contract(
    class_id: int,
    request: ContractCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    classroom, membership = _require_class_teacher(db, class_id, user)
    if request.type == "STUDENT_CLASS_JOIN" and membership.role != "owner":
        raise HTTPException(status_code=403, detail="仅班级 owner 可重置学生加入码")
    max_uses = request.max_uses
    expires_at = request.expires_at
    if request.type == "STUDENT_CLASS_JOIN":
        max_uses = None
        expires_at = None
    else:
        max_uses = max_uses or 1
        expires_at = expires_at or (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7))
    try:
        contract = _create_contract(
            db,
            contract_type=request.type,
            target_id=classroom.id,
            creator_id=user.id,
            expires_at=expires_at,
            max_uses=max_uses,
        )
        if request.type == "STUDENT_CLASS_JOIN":
            classroom.invite_code = contract.code
        db.commit()
        db.refresh(contract)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="生成关系码冲突，请重试")
    return APIResponse(data=_contract_payload(contract))


@router.post("/students/{student_id}/family-contract", response_model=APIResponse)
def create_family_contract(
    student_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user_can_access_student(db, user, student_id):
        raise HTTPException(status_code=404, detail="学生不存在")
    contract = _create_contract(
        db,
        contract_type="FAMILY_BIND",
        target_id=student_id,
        creator_id=user.id,
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=14),
        max_uses=1,
    )
    db.commit()
    db.refresh(contract)
    return APIResponse(data=_contract_payload(contract))


@router.post("/contracts/{code}/claim", response_model=APIResponse)
def claim_contract(
    code: str,
    request: ContractClaimRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    contract = _load_active_contract(db, code)
    if contract.type == "STUDENT_CLASS_JOIN":
        classroom = _classroom(db, contract.target_id)
        if classroom.status != "active":
            raise HTTPException(status_code=409, detail="班级已归档或终止")
        if not request.student_name:
            raise HTTPException(status_code=422, detail="请输入学生姓名")
        own_student_ids = active_student_ids(db, user.id)
        selected_id = request.student_id
        if selected_id is not None:
            if selected_id not in own_student_ids:
                raise HTTPException(status_code=403, detail="当前账号无权选择该学生")
        elif len(own_student_ids) == 1:
            selected_id = own_student_ids[0]
        elif own_student_ids:
            raise HTTPException(status_code=422, detail="请选择本次加入班级的学生")
        elif not user_has_role(db, user, "student"):
            raise HTTPException(status_code=409, detail="请先通过家庭关系码绑定学生")

        query = db.query(StudentRoster).filter(
            StudentRoster.class_id == classroom.id,
            StudentRoster.student_name == request.student_name,
            StudentRoster.status == "active",
            (StudentRoster.bound_user_id.is_(None) | (StudentRoster.bound_user_id == user.id)),
        )
        if selected_id is not None:
            query = query.filter(
                (StudentRoster.student_id.is_(None)) | (StudentRoster.student_id == selected_id)
            )
        if request.roster_id is not None:
            query = query.filter(StudentRoster.id == request.roster_id)
        candidates = query.order_by(StudentRoster.id).all()
        if not candidates:
            raise HTTPException(status_code=404, detail="该姓名未匹配到可加入的本班名册")
        if len(candidates) > 1:
            return APIResponse(data={
                "requires_disambiguation": True,
                "class_id": classroom.id,
                "class_name": classroom.name,
                "candidates": [{
                    "roster_id": row.id,
                    "student_name": row.student_name,
                    "student_no": row.student_no,
                    "disambiguation_note": row.disambiguation_note,
                } for row in candidates],
            })

        roster = db.query(StudentRoster).filter(
            StudentRoster.id == candidates[0].id
        ).with_for_update().first()
        selected_binding = None
        if selected_id is not None:
            selected_binding = db.query(StudentUserBinding).filter(
                StudentUserBinding.student_id == selected_id,
                StudentUserBinding.user_id == user.id,
                StudentUserBinding.status == "active",
            ).first()
        relationship_type = (
            selected_binding.relationship_type
            if selected_binding and request.relationship_type is None
            else (request.relationship_type or "self")
        )
        if relationship_type not in RELATIONSHIP_TYPES:
            raise HTTPException(status_code=422, detail="家庭关系类型无效")
        if selected_binding is None and relationship_type != "self":
            raise HTTPException(status_code=422, detail="请通过家庭关系码建立非本人关系")
        if selected_binding and request.relationship_type and request.relationship_type != selected_binding.relationship_type:
            raise HTTPException(status_code=409, detail="请使用家庭关系码修改家庭关系")
        student = db.query(Student).filter(Student.id == roster.student_id).first() if roster.student_id else None
        if selected_id is not None and student is not None and student.id != selected_id:
            raise HTTPException(status_code=409, detail="该名册已关联其他学生档案")
        if student is None:
            student = Student(name=roster.student_name, status="active")
            db.add(student)
            db.flush()
            roster.student_id = student.id
        if selected_id is not None and student.id != selected_id:
            raise HTTPException(status_code=409, detail="学生档案与目标名册不一致")
        binding = db.query(StudentUserBinding).filter(
            StudentUserBinding.student_id == student.id,
            StudentUserBinding.user_id == user.id,
        ).first()
        if binding is None:
            db.add(StudentUserBinding(
                student_id=student.id,
                user_id=user.id,
                relationship_type=relationship_type,
                relationship_label=request.relationship_label,
                status="active",
            ))
        roster.bound_user_id = user.id if relationship_type == "self" else roster.bound_user_id
        if relationship_type == "self":
            membership = db.query(ClassMember.id).filter(
                ClassMember.class_id == classroom.id,
                ClassMember.student_id == user.id,
            ).first()
            if membership is None:
                db.add(ClassMember(class_id=classroom.id, student_id=user.id))
        _consume(contract)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="关系建立冲突，请刷新后重试")
        return APIResponse(data={
            "joined": True,
            "class_id": classroom.id,
            "class_name": classroom.name,
            "roster_id": roster.id,
            "student_id": student.id,
            "student_name": student.name,
            "relationship_type": relationship_type,
        })

    if contract.type == "FAMILY_BIND":
        student = db.query(Student).filter(Student.id == contract.target_id).first()
        if student is None or student.status != "active":
            raise HTTPException(status_code=404, detail="学生不存在")
        relationship_type = request.relationship_type
        if relationship_type is None:
            raise HTTPException(status_code=422, detail="请选择家庭关系")
        existing = db.query(StudentUserBinding).filter(
            StudentUserBinding.student_id == student.id,
            StudentUserBinding.user_id == user.id,
        ).first()
        if existing and existing.status == "active":
            return APIResponse(data={"bound": True, "already_bound": True, "student_id": student.id})
        if existing:
            existing.status = "active"
            existing.relationship_type = relationship_type
            existing.relationship_label = request.relationship_label
        else:
            db.add(StudentUserBinding(
                student_id=student.id,
                user_id=user.id,
                relationship_type=relationship_type,
                relationship_label=request.relationship_label,
                status="active",
            ))
        _consume(contract)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="家庭关系已被并发建立")
        return APIResponse(data={
            "bound": True,
            "already_bound": False,
            "student_id": student.id,
            "student_name": student.name,
            "relationship_type": relationship_type,
        })

    if contract.type == "TEACHER_CLASS_JOIN":
        if not user_has_role(db, user, "teacher"):
            raise HTTPException(status_code=403, detail="仅教师账号可接受教师邀请")
        classroom = _classroom(db, contract.target_id)
        if classroom.status != "active":
            raise HTTPException(status_code=409, detail="班级已归档或终止")
        teacher = db.query(ClassTeacher).filter(
            ClassTeacher.class_id == classroom.id,
            ClassTeacher.teacher_user_id == user.id,
        ).first()
        if teacher and teacher.status == "active":
            return APIResponse(data={"joined": True, "already_joined": True, "class_id": classroom.id})
        if teacher is None:
            teacher = ClassTeacher(
                class_id=classroom.id,
                teacher_user_id=user.id,
                role="teacher",
                subject_codes_json=request.subject_codes,
                status="active",
            )
            db.add(teacher)
        else:
            teacher.role = "teacher"
            teacher.subject_codes_json = request.subject_codes
            teacher.status = "active"
        _consume(contract)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="教师加入冲突，请刷新后重试")
        return APIResponse(data={
            "joined": True,
            "class_id": classroom.id,
            "class_name": classroom.name,
            "role": teacher.role,
            "subject_codes": teacher.subject_codes_json or [],
        })
    raise HTTPException(status_code=400, detail="不支持的关系码类型")


@router.get("/classes/{class_id}/teachers", response_model=APIResponse)
def list_class_teachers(
    class_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_class_teacher(db, class_id, user)
    rows = (
        db.query(ClassTeacher, User)
        .join(User, User.id == ClassTeacher.teacher_user_id)
        .filter(ClassTeacher.class_id == class_id, ClassTeacher.status == "active")
        .order_by(ClassTeacher.role, ClassTeacher.created_at, ClassTeacher.id)
        .all()
    )
    return APIResponse(data=[{
        "user_id": teacher.id,
        "name": teacher.full_name or teacher.username,
        "role": membership.role,
        "subject_codes": membership.subject_codes_json or [],
    } for membership, teacher in rows])


@router.get("/classes/{class_id}/relation-requests", response_model=APIResponse)
def list_class_relation_requests(
    class_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_owner(db, class_id, user)
    pending_leaves = (
        db.query(StudentRoster, Student)
        .join(Student, Student.id == StudentRoster.student_id)
        .filter(StudentRoster.class_id == class_id, StudentRoster.status == "pending_leave")
        .order_by(Student.name, Student.id)
        .all()
    )
    pending_family = (
        db.query(StudentUserBinding, Student, User)
        .join(Student, Student.id == StudentUserBinding.student_id)
        .join(User, User.id == StudentUserBinding.user_id)
        .join(StudentRoster, StudentRoster.student_id == Student.id)
        .filter(
            StudentRoster.class_id == class_id,
            StudentRoster.status.in_(["active", "pending_leave"]),
            StudentUserBinding.status == "pending_review",
        )
        .distinct()
        .order_by(Student.name, User.id)
        .all()
    )
    return APIResponse(data={
        "student_leave": [{
            "student_id": student.id,
            "student_name": student.name,
        } for _, student in pending_leaves],
        "family_binding": [{
            "binding_id": binding.id,
            "student_id": student.id,
            "student_name": student.name,
            "user_id": account.id,
            "user_name": account.full_name or account.username,
            "relationship_type": binding.relationship_type,
        } for binding, student, account in pending_family],
    })


@router.post("/classes/{class_id}/teachers/{teacher_user_id}/remove", response_model=APIResponse)
def remove_class_teacher(
    class_id: int,
    teacher_user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_owner(db, class_id, user)
    membership = db.query(ClassTeacher).filter(
        ClassTeacher.class_id == class_id,
        ClassTeacher.teacher_user_id == teacher_user_id,
        ClassTeacher.status == "active",
    ).with_for_update().first()
    if membership is None:
        raise HTTPException(status_code=404, detail="教师关系不存在")
    if membership.role == "owner":
        raise HTTPException(status_code=409, detail="请先转移班级 owner")
    membership.status = "removed"
    db.commit()
    return APIResponse(data={"removed": True, "teacher_user_id": teacher_user_id})


@router.post("/classes/{class_id}/teachers/leave", response_model=APIResponse)
def leave_class_as_teacher(
    class_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _, membership = _require_class_teacher(db, class_id, user)
    if membership.role == "owner":
        raise HTTPException(status_code=409, detail="owner 必须先转移 owner 或解散班级")
    membership.status = "left"
    db.commit()
    return APIResponse(data={"left": True, "class_id": class_id})


@router.post("/classes/{class_id}/owner-transfer", response_model=APIResponse)
def transfer_class_owner(
    class_id: int,
    request: OwnerTransferRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    locked_classroom = db.query(Class).filter(Class.id == class_id).with_for_update().first()
    if locked_classroom is None:
        raise HTTPException(status_code=404, detail="班级不存在")
    classroom, owner = _require_owner(db, class_id, user)
    if request.teacher_user_id == user.id:
        raise HTTPException(status_code=422, detail="新 owner 必须是另一位有效教师")
    target = db.query(ClassTeacher).filter(
        ClassTeacher.class_id == class_id,
        ClassTeacher.teacher_user_id == request.teacher_user_id,
        ClassTeacher.status == "active",
    ).with_for_update().first()
    target_user = db.query(User).filter(User.id == request.teacher_user_id).first()
    if target is None or target_user is None or not user_has_role(db, target_user, "teacher"):
        raise HTTPException(status_code=404, detail="目标教师不是本班有效教师")
    owner.role = "teacher"
    target.role = "owner"
    classroom.teacher_id = target.teacher_user_id
    db.commit()
    return APIResponse(data={"owner_user_id": classroom.teacher_id})


@router.post("/classes/{class_id}/status", response_model=APIResponse)
def update_class_status(
    class_id: int,
    request: ClassStatusRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    classroom, _ = _require_owner(db, class_id, user)
    classroom.status = request.status
    db.commit()
    return APIResponse(data={"class_id": class_id, "status": classroom.status})


@router.post("/classes/{class_id}/students/{student_id}/remove", response_model=APIResponse)
def remove_student_from_class(
    class_id: int,
    student_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_owner(db, class_id, user)
    roster = db.query(StudentRoster).filter(
        StudentRoster.class_id == class_id,
        StudentRoster.student_id == student_id,
        StudentRoster.status == "active",
    ).with_for_update().first()
    if roster is None:
        raise HTTPException(status_code=404, detail="本班学生关系不存在")
    roster.status = "removed"
    db.commit()
    return APIResponse(data={"removed": True, "student_id": student_id})


@router.post("/students/{student_id}/classes/{class_id}/leave", response_model=APIResponse)
def request_student_class_leave(
    student_id: int,
    class_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user_can_access_student(db, user, student_id):
        raise HTTPException(status_code=404, detail="学生不存在")
    roster = db.query(StudentRoster).filter(
        StudentRoster.student_id == student_id,
        StudentRoster.class_id == class_id,
        StudentRoster.status == "active",
    ).with_for_update().first()
    if roster is None:
        raise HTTPException(status_code=404, detail="学生不属于该班级")
    roster.status = "pending_leave"
    db.commit()
    return APIResponse(data={"status": "pending_leave", "student_id": student_id})


@router.post("/classes/{class_id}/students/{student_id}/leave-review", response_model=APIResponse)
def review_student_leave(
    class_id: int,
    student_id: int,
    request: StudentLeaveReviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_owner(db, class_id, user)
    roster = db.query(StudentRoster).filter(
        StudentRoster.class_id == class_id,
        StudentRoster.student_id == student_id,
        StudentRoster.status == "pending_leave",
    ).with_for_update().first()
    if roster is None:
        raise HTTPException(status_code=404, detail="未找到待处理的退出请求")
    roster.status = "left" if request.approve else "active"
    db.commit()
    return APIResponse(data={"student_id": student_id, "status": roster.status})


@router.post("/students/{student_id}/family-bindings/{user_id}/remove", response_model=APIResponse)
def remove_family_binding(
    student_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.id != user_id and not user_has_role(db, user, "platform_admin"):
        raise HTTPException(status_code=403, detail="只能撤回自己的家庭关系")
    binding = db.query(StudentUserBinding).filter(
        StudentUserBinding.student_id == student_id,
        StudentUserBinding.user_id == user_id,
        StudentUserBinding.status == "active",
    ).with_for_update().first()
    if binding is None:
        raise HTTPException(status_code=404, detail="家庭关系不存在")
    count = db.query(StudentUserBinding.id).filter(
        StudentUserBinding.student_id == student_id,
        StudentUserBinding.status == "active",
    ).count()
    if count <= 1:
        binding.status = "pending_review"
        db.commit()
        return APIResponse(data={"requires_review": True, "status": "pending_review"})
    binding.status = "revoked"
    db.commit()
    return APIResponse(data={"requires_review": False, "status": "revoked"})


@router.post("/students/{student_id}/family-bindings/{user_id}/review", response_model=APIResponse)
def review_family_binding(
    student_id: int,
    user_id: int,
    request: RelationshipReviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user_has_role(db, user, "platform_admin"):
        class_ids = [row[0] for row in db.query(StudentRoster.class_id).filter(
            StudentRoster.student_id == student_id,
            StudentRoster.status.in_(["active", "pending_leave"]),
        ).all()]
        if not any((member := _class_role(db, class_id, user.id)) and member.role == "owner" for class_id in class_ids):
            raise HTTPException(status_code=403, detail="仅该学生活跃班级 owner 或平台管理员可审核")
    binding = db.query(StudentUserBinding).filter(
        StudentUserBinding.student_id == student_id,
        StudentUserBinding.user_id == user_id,
        StudentUserBinding.status == "pending_review",
    ).with_for_update().first()
    if binding is None:
        raise HTTPException(status_code=404, detail="未找到待审核家庭关系")
    binding.status = "revoked" if request.approve else "active"
    db.commit()
    return APIResponse(data={"status": binding.status})
