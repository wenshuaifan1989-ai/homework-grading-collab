"""Student-scoped resolution for differentiated assignment content."""

from models.classroom import Assignment
from models.learning import (
    AssignmentVariant,
    AssignmentVariantQuestion,
    AssignmentVariantSet,
    AssignmentVariantTask,
    StudentSubjectTier,
)


def change_student_tier(db, *, student_id, class_id, subject, level, actor_id):
    """Shared 012/014 writer; callers enforce teacher/class/subject authority."""
    from models.identity_relations import Student
    from models.learning import StudentSubjectTierAudit
    if level not in {'L1','L2','L3'}:
        raise ValueError('Invalid tier')
    db.query(Student).filter_by(id=student_id).with_for_update().one()
    tier=db.query(StudentSubjectTier).filter_by(student_id=student_id,class_id=class_id,subject=subject).with_for_update().first()
    old=tier.level if tier else None
    if old==level:
        return None
    if tier is None:
        db.add(StudentSubjectTier(student_id=student_id,class_id=class_id,subject=subject,level=level,updated_by=actor_id))
    else:
        tier.level=level;tier.updated_by=actor_id
    audit=StudentSubjectTierAudit(student_id=student_id,class_id=class_id,subject=subject,from_level=old,to_level=level,actor_user_id=actor_id)
    db.add(audit);db.flush()
    return audit


def current_assignment_variant(db, assignment_id: int, level: str) -> AssignmentVariant | None:
    return db.query(AssignmentVariant).filter(
        AssignmentVariant.assignment_id == assignment_id,
        AssignmentVariant.level == level,
        AssignmentVariant.is_current.is_(True),
    ).first()


def resolve_assignment_variant(db, assignment: Assignment, student_id: int, task_id: str | None = None):
    variant_set = db.query(AssignmentVariantSet).filter_by(
        assignment_id=assignment.id
    ).first()
    if variant_set is None:
        return None, None

    from services.teacher_v2 import publication_for
    publication = publication_for(db, assignment.id)
    if publication:
        if str(student_id) not in publication.snapshot['requirements']:
            return variant_set, None
        return variant_set, db.get(AssignmentVariant, publication.variant_id)

    if task_id:
        submitted = db.query(AssignmentVariantTask).filter_by(task_id=task_id).first()
        if submitted is not None:
            selected = db.query(AssignmentVariant).filter_by(id=submitted.variant_id).first()
            return variant_set, selected

    tier = db.query(StudentSubjectTier).filter_by(
        student_id=student_id,
        class_id=assignment.class_id,
        subject=assignment.subject,
    ).first()
    level = tier.level if tier else (
        variant_set.fallback_level if variant_set.allow_uniform_fallback else None
    )
    if level is None:
        return variant_set, None
    return variant_set, current_assignment_variant(db, assignment.id, level)


def student_assignment_variant_fields(db, assignment: Assignment, student_id: int, task_id: str | None = None) -> dict:
    from services.teacher_v2 import publication_for, student_fields
    publication = publication_for(db, assignment.id)
    if publication:
        return student_fields(publication, student_id)
    variant_set, variant = resolve_assignment_variant(db, assignment, student_id, task_id)
    if variant_set is None:
        return {}
    if variant is None:
        return {
            "variant_mode": True,
            "variant_available": False,
            "variant_questions": [],
            "variant_message": "老师尚未为当前学生准备好这项作业，请联系老师。",
        }

    questions = db.query(AssignmentVariantQuestion).filter_by(
        variant_id=variant.id
    ).order_by(AssignmentVariantQuestion.sort_order, AssignmentVariantQuestion.id).all()
    return {
        "variant_mode": True,
        "variant_available": bool(questions),
        "variant_questions": [
            {
                "id": question.id,
                "number": index + 1,
                "question_text": question.question_text,
                "options": (
                    [f"{key}. {value}" for key, value in question.options_json.items()]
                    if isinstance(question.options_json, dict)
                    else question.options_json
                ),
                "max_score": float(question.max_score),
            }
            for index, question in enumerate(questions)
        ],
        "variant_message": None if questions else "老师尚未为当前学生准备好这项作业，请联系老师。",
    }
