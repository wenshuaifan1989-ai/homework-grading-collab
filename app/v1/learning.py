"""012 teacher-managed subject tiers and differentiated assignment variants."""

from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.v1.classroom import _teacher_assignment, _teacher_class
from models.classroom import Assignment, StudentRoster
from models.identity_relations import ClassTeacher
from models.learning import (
    AssignmentVariant,
    AssignmentVariantQuestion,
    AssignmentVariantSet,
    StudentSubjectTier,
    StudentSubjectTierAudit,
)
from models.paper import QuestionAsset
from models.user import User
from schemas.common import APIResponse
from schemas.learning import AssignmentVariantsUpsertRequest, SubjectTierBatchRequest
from services.identity_relations import user_has_role
from services.learning import current_assignment_variant
from utils.database import get_db
from utils.deps import get_current_user


router = APIRouter(prefix="/learning", tags=["012 学科分层与分层作业"])
LEVEL_LABELS = {"L1": "基础巩固", "L2": "稳定提升", "L3": "拓展挑战"}


def _require_teacher(db: Session, user: User) -> None:
    if not user_has_role(db, user, "teacher"):
        raise HTTPException(status_code=403, detail="只有教师账号可以管理学科分层与分层作业")


def _teacher_subject_class(db: Session, user: User, class_id: int, subject: str):
    classroom = _teacher_class(db, class_id, user.id)
    membership = db.query(ClassTeacher).filter_by(
        class_id=class_id, teacher_user_id=user.id, status="active"
    ).first()
    if membership and membership.subject_codes_json and subject not in membership.subject_codes_json:
        raise HTTPException(status_code=403, detail="当前教师无权管理该学科")
    return classroom


def _assignment_for_teacher(db: Session, user: User, assignment_id: int) -> Assignment:
    assignment = _teacher_assignment(db, assignment_id, user.id)
    _teacher_subject_class(db, user, assignment.class_id, assignment.subject)
    return assignment


def _tier_rows(db: Session, class_id: int, subject: str) -> list[dict]:
    tiers = {
        row.student_id: row
        for row in db.query(StudentSubjectTier).filter_by(class_id=class_id, subject=subject).all()
    }
    roster = db.query(StudentRoster).filter_by(class_id=class_id, status="active").order_by(
        StudentRoster.student_name, StudentRoster.id
    ).all()
    return [
        {
            "roster_id": row.id,
            "student_id": row.student_id,
            "student_name": row.student_name,
            "student_no": row.student_no,
            "level": tiers[row.student_id].level if row.student_id in tiers else None,
            "level_label": LEVEL_LABELS.get(tiers[row.student_id].level) if row.student_id in tiers else "待分层",
            "updated_at": tiers[row.student_id].updated_at if row.student_id in tiers else None,
        }
        for row in roster
    ]


@router.get("/classes/{class_id}/tiers", response_model=APIResponse)
def list_subject_tiers(
    class_id: int,
    subject: str = Query(min_length=1, max_length=40),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_teacher(db, user)
    normalized = subject.strip().lower()
    if not normalized:
        raise HTTPException(status_code=422, detail="学科不能为空")
    _teacher_subject_class(db, user, class_id, normalized)
    return APIResponse(data={"class_id": class_id, "subject": normalized, "students": _tier_rows(db, class_id, normalized)})


@router.put("/classes/{class_id}/tiers", response_model=APIResponse)
def set_subject_tiers(
    class_id: int,
    request: SubjectTierBatchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_teacher(db, user)
    _teacher_subject_class(db, user, class_id, request.subject)
    ids = [entry.student_id for entry in request.entries]
    roster = db.query(StudentRoster).filter(
        StudentRoster.class_id == class_id,
        StudentRoster.status == "active",
        StudentRoster.student_id.in_(ids),
    ).all()
    roster_by_student = {row.student_id: row for row in roster if row.student_id is not None}
    if set(ids) != set(roster_by_student):
        raise HTTPException(status_code=404, detail="所选学生不属于当前班级有效名册或尚未绑定学生身份")

    changed = 0
    for entry in request.entries:
        from services.learning import change_student_tier
        audit = change_student_tier(db, student_id=entry.student_id, class_id=class_id,
                                    subject=request.subject, level=entry.level, actor_id=user.id)
        changed += int(audit is not None)
    db.commit()
    return APIResponse(data={
        "class_id": class_id,
        "subject": request.subject,
        "changed_count": changed,
        "students": _tier_rows(db, class_id, request.subject),
    })


@router.get("/classes/{class_id}/tier-history", response_model=APIResponse)
def subject_tier_history(
    class_id: int,
    subject: str = Query(min_length=1, max_length=40),
    student_id: int = Query(gt=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_teacher(db, user)
    normalized = subject.strip().lower()
    _teacher_subject_class(db, user, class_id, normalized)
    if db.query(StudentRoster.id).filter_by(
        class_id=class_id, student_id=student_id, status="active"
    ).first() is None:
        raise HTTPException(status_code=404, detail="学生不属于当前班级有效名册")
    rows = db.query(StudentSubjectTierAudit).filter_by(
        class_id=class_id, subject=normalized, student_id=student_id
    ).order_by(StudentSubjectTierAudit.changed_at.desc(), StudentSubjectTierAudit.id.desc()).limit(limit).all()
    return APIResponse(data={
        "student_id": student_id,
        "class_id": class_id,
        "subject": normalized,
        "items": [{
            "from_level": row.from_level,
            "to_level": row.to_level,
            "actor_user_id": row.actor_user_id,
            "changed_at": row.changed_at,
        } for row in rows],
    })


def _teacher_variant_payload(db: Session, variant: AssignmentVariant) -> dict:
    questions = db.query(AssignmentVariantQuestion).filter_by(variant_id=variant.id).order_by(
        AssignmentVariantQuestion.sort_order, AssignmentVariantQuestion.id
    ).all()
    return {
        "id": variant.id,
        "level": variant.level,
        "level_label": LEVEL_LABELS[variant.level],
        "version": variant.version,
        "questions": [{
            "id": row.id,
            "source_type": row.source_type,
            "source_asset_id": row.source_asset_id,
            "sort_order": row.sort_order,
            "question_text": row.question_text,
            "options": row.options_json,
            "correct_answer": row.correct_answer,
            "analysis": row.analysis,
            "max_score": float(row.max_score),
        } for row in questions],
    }


@router.get("/assignments/{assignment_id}/variants", response_model=APIResponse)
def get_assignment_variants(
    assignment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_teacher(db, user)
    assignment = _assignment_for_teacher(db, user, assignment_id)
    variant_set = db.query(AssignmentVariantSet).filter_by(assignment_id=assignment.id).first()
    variants = db.query(AssignmentVariant).filter_by(
        assignment_id=assignment.id, is_current=True
    ).order_by(AssignmentVariant.level).all()
    return APIResponse(data={
        "assignment_id": assignment.id,
        "allow_uniform_fallback": variant_set.allow_uniform_fallback if variant_set else False,
        "uniform_fallback_level": variant_set.fallback_level if variant_set else None,
        "variants": [_teacher_variant_payload(db, variant) for variant in variants],
    })


@router.put("/assignments/{assignment_id}/variants", response_model=APIResponse)
def upsert_assignment_variants(
    assignment_id: int,
    request: AssignmentVariantsUpsertRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_teacher(db, user)
    assignment = _assignment_for_teacher(db, user, assignment_id)
    from services.teacher_v2 import publication_for
    if publication_for(db, assignment.id):
        raise HTTPException(409, '单套原卷发布快照不可通过旧三版本入口改写，请新建作业')
    variant_set = db.query(AssignmentVariantSet).filter_by(
        assignment_id=assignment.id
    ).with_for_update().first()
    if variant_set is None:
        variant_set = AssignmentVariantSet(
            assignment_id=assignment.id,
            allow_uniform_fallback=request.allow_uniform_fallback,
            fallback_level=request.uniform_fallback_level,
            updated_by=user.id,
        )
        db.add(variant_set)
    else:
        variant_set.allow_uniform_fallback = request.allow_uniform_fallback
        variant_set.fallback_level = request.uniform_fallback_level
        variant_set.updated_by = user.id

    new_variants = []
    try:
        for definition in request.variants:
            existing = current_assignment_variant(db, assignment.id, definition.level)
            highest_version = db.query(func.max(AssignmentVariant.version)).filter_by(
                assignment_id=assignment.id, level=definition.level
            ).scalar() or 0
            if existing:
                existing.is_current = False
            variant = AssignmentVariant(
                assignment_id=assignment.id,
                level=definition.level,
                version=int(highest_version) + 1,
                is_current=True,
                updated_by=user.id,
            )
            db.add(variant)
            db.flush()

            for order, question in enumerate(definition.questions, start=1):
                source_type = "MANUAL"
                source_asset_id = None
                question_text = question.question_text
                options = question.options
                correct_answer = question.correct_answer
                analysis = question.analysis
                if question.source_asset_id is not None:
                    asset = db.query(QuestionAsset).filter(
                        QuestionAsset.id == question.source_asset_id,
                        QuestionAsset.review_status == "CONFIRMED",
                        QuestionAsset.subject == assignment.subject,
                        QuestionAsset.grade == assignment.grade,
                    ).first()
                    if asset is None or not (asset.question_text or "").strip():
                        raise HTTPException(
                            status_code=422,
                            detail="只能使用已由教师确认、且学科年级与作业一致的题目资产",
                        )
                    if asset.source=='teacher_v2' and not (asset.rights_reference or '').startswith(f'teacher:{user.id}:'):
                        raise HTTPException(404,'题目不存在')
                    source_type = "ASSET"
                    source_asset_id = asset.id
                    question_text = asset.question_text
                    options = asset.options_json
                    correct_answer = asset.correct_answer
                    analysis = asset.analysis
                db.add(AssignmentVariantQuestion(
                    variant_id=variant.id,
                    source_type=source_type,
                    source_asset_id=source_asset_id,
                    sort_order=order,
                    question_text=(question_text or "").strip(),
                    options_json=options,
                    correct_answer=correct_answer,
                    analysis=analysis,
                    max_score=Decimal(str(question.max_score)),
                ))
            new_variants.append(variant)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return APIResponse(data={
        "assignment_id": assignment.id,
        "allow_uniform_fallback": variant_set.allow_uniform_fallback,
        "uniform_fallback_level": variant_set.fallback_level,
        "variants": [_teacher_variant_payload(db, variant) for variant in new_variants],
    })


def _variant_pdf(assignment: Assignment, variant: AssignmentVariant, questions: list[AssignmentVariantQuestion]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    font_name = "STSong-Light"
    if font_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(font_name))
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "VariantTitle", parent=styles["Title"], fontName=font_name,
        fontSize=18, leading=24, alignment=TA_CENTER, textColor=colors.HexColor("#172554"),
    )
    meta_style = ParagraphStyle(
        "VariantMeta", parent=styles["Normal"], fontName=font_name,
        fontSize=10, leading=16, textColor=colors.HexColor("#475569"), alignment=TA_LEFT,
    )
    question_style = ParagraphStyle(
        "VariantQuestion", parent=styles["Normal"], fontName=font_name,
        fontSize=12, leading=20, spaceAfter=8, wordWrap="CJK",
    )
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=48, leftMargin=48, topMargin=54, bottomMargin=48,
        title=assignment.title,
    )
    story = [Paragraph(escape(assignment.title), title_style), Spacer(1, 12)]
    meta = f"学科：{escape(assignment.subject)}　年级：{escape(assignment.grade)}"
    story.extend([Paragraph(meta, meta_style), Spacer(1, 18)])
    for index, question in enumerate(questions, start=1):
        text = escape(question.question_text).replace("\r\n", "\n").replace("\n", "<br/>")
        story.append(Paragraph(f"{index}. {text}", question_style))
        if question.options_json:
            options = question.options_json
            if isinstance(options, dict):
                option_text = "　".join(f"{escape(str(k))}. {escape(str(v))}" for k, v in options.items())
            else:
                option_text = "　".join(escape(str(value)) for value in options)
            story.append(Paragraph(option_text, meta_style))
        story.append(Paragraph(f"（本题 {float(question.max_score):g} 分）", meta_style))
        story.append(Spacer(1, 14))
    if not questions:
        raise HTTPException(status_code=409, detail="当前版本没有可打印题目")
    doc.build(story)
    return buffer.getvalue()


@router.get("/assignments/{assignment_id}/variants/{level}/print.pdf")
def print_assignment_variant(
    assignment_id: int,
    level: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_teacher(db, user)
    assignment = _assignment_for_teacher(db, user, assignment_id)
    from services.teacher_v2 import publication_for
    if publication_for(db, assignment.id):
        raise HTTPException(409, '请通过作业详情下载同一原卷，不能重新排版替换发布原卷')
    normalized_level = level.upper()
    if normalized_level not in LEVEL_LABELS:
        raise HTTPException(status_code=404, detail="版本不存在")
    variant = current_assignment_variant(db, assignment.id, normalized_level)
    if variant is None:
        raise HTTPException(status_code=404, detail="版本不存在")
    questions = db.query(AssignmentVariantQuestion).filter_by(variant_id=variant.id).order_by(
        AssignmentVariantQuestion.sort_order, AssignmentVariantQuestion.id
    ).all()
    # Registered choice papers use exact stem-bracket coordinates. Legacy
    # non-choice exports stay byte-layout compatible with the original path.
    if questions and all(q.options_json and q.source_asset_id for q in questions):
        from pathlib import Path
        from services.known_assignment_templates import generate
        from models.known_assignment import PageTemplate
        uploaded = db.query(PageTemplate).filter_by(variant_id=variant.id,status='ACTIVE',source='uploaded').first()
        if uploaded:
            if not uploaded.pdf_locator:
                raise HTTPException(409, '已使用上传图片模板，请在括号复核页下载原页')
            content = Path(uploaded.pdf_locator).read_bytes()
        else:
            try:
                pages = generate(db, assignment, variant, user.id)
                content = Path(pages[0].pdf_locator).read_bytes()
            except ValueError as exc:
                raise HTTPException(409, str(exc))
    else:
        content = _variant_pdf(assignment, variant, questions)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="practice.pdf"'},
    )
