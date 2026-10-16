from sqlalchemy.orm import Session

from models.classroom import StudentRoster
from models.identity_relations import ClassTeacher, Student, StudentUserBinding
from models.user import User
from models.user_role import UserRole


LEGACY_ROLE_CODES = {"admin": "platform_admin", "teacher": "teacher", "student": "student"}


def user_role_codes(db: Session, user: User) -> set[str]:
    codes = {
        row[0]
        for row in db.query(UserRole.role_code).filter(
            UserRole.user_id == user.id, UserRole.status == "active"
        )
    }
    legacy = LEGACY_ROLE_CODES.get(user.role)
    if legacy:
        codes.add(legacy)
    return codes


def user_has_role(db: Session, user: User, role_code: str) -> bool:
    return role_code in user_role_codes(db, user)


def active_student_ids(db: Session, user_id: int) -> list[int]:
    return [
        int(row[0])
        for row in db.query(StudentUserBinding.student_id)
        .filter(
            StudentUserBinding.user_id == user_id,
            StudentUserBinding.status == "active",
        )
        .order_by(StudentUserBinding.student_id)
        .all()
    ]


def user_can_access_student(
    db: Session,
    user: User,
    student_id: int,
    *,
    class_id: int | None = None,
) -> bool:
    student = db.query(Student.id).filter(
        Student.id == student_id,
        Student.status == "active",
    ).first()
    if student is None:
        return False
    if user_has_role(db, user, "platform_admin"):
        return True
    binding = db.query(StudentUserBinding.id).filter(
        StudentUserBinding.user_id == user.id,
        StudentUserBinding.student_id == student_id,
        StudentUserBinding.status == "active",
    ).first()
    if binding:
        return True
    if class_id is None:
        return False
    teacher = db.query(ClassTeacher.id).filter(
        ClassTeacher.class_id == class_id,
        ClassTeacher.teacher_user_id == user.id,
        ClassTeacher.status == "active",
    ).first()
    if teacher:
        return db.query(StudentRoster.id).filter(
            StudentRoster.class_id == class_id,
            StudentRoster.student_id == student_id,
            StudentRoster.status == "active",
        ).first() is not None
    return False


def roster_student_for_user(db: Session, user_id: int, class_id: int) -> list[int]:
    return [
        int(row[0])
        for row in db.query(StudentRoster.student_id)
        .join(
            StudentUserBinding,
            StudentUserBinding.student_id == StudentRoster.student_id,
        )
        .filter(
            StudentRoster.class_id == class_id,
            StudentRoster.status == "active",
            StudentRoster.student_id.is_not(None),
            StudentUserBinding.user_id == user_id,
            StudentUserBinding.status == "active",
        )
        .distinct()
        .order_by(StudentRoster.student_id)
        .all()
    ]
