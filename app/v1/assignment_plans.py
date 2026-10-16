"""013 manual question selection, editable plans and teacher-confirmed publishing."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.v1.classroom import _teacher_class
from app.v1.learning import LEVEL_LABELS, _variant_pdf
from models.assignment_plan import AssignmentPlan, AssignmentPlanQuestion
from models.classroom import Assignment, Class
from models.identity_relations import ClassTeacher
from models.learning import AssignmentVariant, AssignmentVariantQuestion, AssignmentVariantSet
from models.paper import QuestionAsset
from models.user import User
from schemas.assignment_plan import AIPlanPromptRequest, AssignmentPlanCreate
from schemas.common import APIResponse
from services.identity_relations import user_has_role
from services.question_bank_provider import (
    PROVIDER_NAME,
    PROVIDER_VERSION,
    RIGHTS_BASES,
    import_local_original_questions,
    question_bank_provider,
)
from utils.database import get_db
from utils.deps import get_current_user


router = APIRouter(prefix="/assignment-plans", tags=["013 题库与 AI 作业助手"])
LEVELS = ("L1", "L2", "L3")


def _teacher_subject_class(db: Session, user: User, class_id: int, subject: str) -> Class:
    if not user_has_role(db, user, "teacher"):
        raise HTTPException(status_code=403, detail="只有教师账号可以管理作业计划")
    classroom = _teacher_class(db, class_id, user.id)
    membership = db.query(ClassTeacher).filter_by(
        class_id=class_id, teacher_user_id=user.id, status="active"
    ).first()
    if membership and membership.subject_codes_json and subject not in membership.subject_codes_json:
        raise HTTPException(status_code=403, detail="当前教师无权管理该学科")
    return classroom


def _owned_plan(db: Session, user: User, plan_id: int, *, lock: bool = False) -> AssignmentPlan:
    query = db.query(AssignmentPlan).filter(
        AssignmentPlan.id == plan_id,
        AssignmentPlan.teacher_user_id == user.id,
    )
    if lock:
        query = query.with_for_update()
    plan = query.first()
    if plan is None:
        raise HTTPException(status_code=404, detail="作业计划不存在")
    _teacher_subject_class(db, user, plan.class_id, plan.subject)
    return plan


def _asset_snapshot(asset: QuestionAsset) -> dict:
    knowledge_points = asset.knowledge_points_json or []
    if (
        asset.rights_basis not in RIGHTS_BASES
        or not (asset.rights_reference or "").strip()
        or not (asset.question_text or "").strip()
        or not (asset.question_type or "").strip()
        or not (asset.correct_answer or "").strip()
        or not (asset.analysis or "").strip()
        or asset.difficulty not in {"easy", "medium", "hard"}
        or asset.review_status not in {"PENDING_REVIEW", "CONFIRMED"}
        or not isinstance(knowledge_points, list)
        or any(not isinstance(point, str) or not point.strip() for point in knowledge_points)
        or (asset.options_json is not None and not isinstance(asset.options_json, (list, dict)))
    ):
        raise HTTPException(status_code=422, detail="题目来源许可、审核状态或内容不满足作业计划要求")
    return {
        "source_asset_id": asset.id,
        "subject": asset.subject,
        "grade": asset.grade,
        "question_text": asset.question_text,
        "question_type": asset.question_type,
        "options": asset.options_json,
        "correct_answer": asset.correct_answer,
        "analysis": asset.analysis,
        "difficulty": asset.difficulty,
        "knowledge_points": knowledge_points,
        "rights_basis": asset.rights_basis,
        "rights_reference": asset.rights_reference,
        "review_status_at_selection": asset.review_status,
    }


def _questions_for_request(db: Session, request: AssignmentPlanCreate, teacher_id: int | None = None) -> list[tuple[str, int, int, dict]]:
    questions = []
    for variant in request.variants:
        for position, selected in enumerate(variant.questions, start=1):
            asset = question_bank_provider.get_question(db, selected.source_asset_id, teacher_id=teacher_id)
            if asset is None:
                raise HTTPException(status_code=422, detail="所选题目不存在、来源未授权或状态不可用")
            if asset.subject != request.subject or asset.grade != request.grade:
                raise HTTPException(status_code=422, detail="所选题目学科或年级与作业计划不一致")
            snapshot = _asset_snapshot(asset)
            if request.question_types and asset.question_type not in request.question_types:
                raise HTTPException(status_code=422, detail="所选题型不符合计划范围")
            if request.difficulty != "mixed" and asset.difficulty != request.difficulty:
                raise HTTPException(status_code=422, detail="所选题目难度不符合计划范围")
            questions.append((variant.level, position, selected.max_score, snapshot))
    return questions


def _request_fingerprint(request: AssignmentPlanCreate) -> str:
    encoded = json.dumps(
        request.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _replace_questions(
    db: Session, plan: AssignmentPlan, questions: list[tuple[str, int, int, dict]],
) -> None:
    db.query(AssignmentPlanQuestion).filter_by(plan_id=plan.id).delete(synchronize_session=False)
    for level, position, max_score, snapshot in questions:
        db.add(AssignmentPlanQuestion(
            plan_id=plan.id,
            level=level,
            sort_order=position,
            source_asset_id=snapshot["source_asset_id"],
            question_snapshot_json=snapshot,
            max_score=max_score,
        ))


def _plan_payload(db: Session, plan: AssignmentPlan, *, rows=None) -> dict:
    if rows is None:
        rows = db.query(AssignmentPlanQuestion).filter_by(plan_id=plan.id).order_by(
            AssignmentPlanQuestion.level, AssignmentPlanQuestion.sort_order
        ).all()
    return {
        "id": plan.id,
        "idempotency_key": plan.idempotency_key,
        "class_id": plan.class_id,
        "assignment_id": plan.assignment_id,
        "title": plan.title,
        "description": plan.description,
        "subject": plan.subject,
        "grade": plan.grade,
        "assignment_date": plan.assignment_date,
        "due_at": plan.due_at,
        "target_knowledge_points": plan.target_knowledge_points_json or [],
        "question_types": plan.question_types_json or [],
        "question_count_per_tier": plan.requested_question_count,
        "difficulty": plan.difficulty,
        "duration_minutes": plan.duration_minutes,
        "tier_strategy": plan.tier_strategy_json,
        "source_mode": plan.source_mode,
        "source_provider": plan.source_provider,
        "source_version": plan.source_version,
        "status": plan.status,
        "variants": [{
            "level": level,
            "level_label": LEVEL_LABELS[level],
            "questions": [{
                "id": row.source_asset_id,
                "source_asset_id": row.source_asset_id,
                "sort_order": row.sort_order,
                "max_score": row.max_score,
                **row.question_snapshot_json,
            } for row in rows if row.level == level],
        } for level in LEVELS],
        "confirmed_by": plan.confirmed_by,
        "confirmed_at": plan.confirmed_at,
        "published_at": plan.published_at,
    }


def _validate_class_grade(classroom: Class, grade: str) -> None:
    if classroom.grade and classroom.grade.strip().lower() != grade.strip().lower():
        raise HTTPException(status_code=422, detail="作业计划年级与班级年级不一致")


@router.get("/ai-status", response_model=APIResponse)
def ai_plan_status(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user_has_role(db, user, "teacher"):
        raise HTTPException(status_code=403, detail="只有教师账号可以查看 AI 作业助手状态")
    return APIResponse(data={
        "status": "PENDING_AUTHORIZATION",
        "enabled": False,
        "daily_request_limit": 0,
        "model_request_sent": False,
        "message": "外部文本模型尚未获得本轮授权；AI提案保持关闭，未发送模型请求。",
    })


@router.post("/ai-proposal", response_model=APIResponse)
def create_ai_proposal(
    request: AIPlanPromptRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    classroom = _teacher_subject_class(db, user, request.class_id, request.subject.strip().lower())
    _validate_class_grade(classroom, request.grade.strip().lower())
    raise HTTPException(
        status_code=409,
        detail={
            "code": "AI_TEXT_PENDING_AUTHORIZATION",
            "message": "当前 AI 作业计划的外部模型额度为0；未发送模型请求。请先使用教师自主选题，AI提案待明确授权后接入。",
            "model_request_sent": False,
        },
    )


@router.post("/question-bank/import-local", response_model=APIResponse)
def import_local_question_bank(
    subject: str = Query(min_length=1, max_length=40),
    grade: str = Query(min_length=1, max_length=40),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user_has_role(db, user, "teacher"):
        raise HTTPException(status_code=403, detail="只有教师账号可以导入本地题库")
    try:
        result = import_local_original_questions(db, subject=subject, grade=grade)
        db.commit()
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return APIResponse(data={
        **result,
        "provider": PROVIDER_NAME,
        "version": PROVIDER_VERSION,
        "review_status": "PENDING_REVIEW",
    })


@router.get("/question-bank/search", response_model=APIResponse)
def search_question_bank(
    class_id: int = Query(gt=0),
    subject: str = Query(min_length=1, max_length=40),
    grade: str = Query(min_length=1, max_length=40),
    query: str = Query(default="", max_length=300),
    difficulty: str | None = Query(default=None, pattern="^(easy|medium|hard)$"),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _teacher_subject_class(db, user, class_id, subject.strip().lower())
    assets = question_bank_provider.search_questions(
        db, subject=subject, grade=grade, query=query, difficulty=difficulty, limit=limit, teacher_id=user.id
    )
    return APIResponse(data={
        "provider": question_bank_provider.name,
        "provider_version": question_bank_provider.version,
        "items": [{
            "id": asset.id,
            "subject": asset.subject,
            "grade": asset.grade,
            "question_text": asset.question_text,
            "question_type": asset.question_type,
            "options": asset.options_json,
            "correct_answer": asset.correct_answer,
            "analysis": asset.analysis,
            "difficulty": asset.difficulty,
            "knowledge_points": asset.knowledge_points_json or [],
            "review_status": asset.review_status,
            "rights_basis": asset.rights_basis,
            "rights_reference": asset.rights_reference,
        } for asset in assets],
    })


@router.get("", response_model=APIResponse)
def list_assignment_plans(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user_has_role(db, user, "teacher"):
        raise HTTPException(status_code=403, detail="只有教师账号可以查看作业计划")
    plans = db.query(AssignmentPlan).filter_by(teacher_user_id=user.id).order_by(
        AssignmentPlan.created_at.desc(), AssignmentPlan.id.desc()
    ).limit(100).all()
    return APIResponse(data=[_plan_payload(db, plan) for plan in plans])


@router.post("", response_model=APIResponse)
def create_assignment_plan(
    request: AssignmentPlanCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    classroom = _teacher_subject_class(db, user, request.class_id, request.subject)
    _validate_class_grade(classroom, request.grade)
    fingerprint = _request_fingerprint(request)
    existing = db.query(AssignmentPlan).filter_by(
        teacher_user_id=user.id, idempotency_key=request.idempotency_key
    ).first()
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="幂等键已用于另一份计划")
        return APIResponse(data=_plan_payload(db, existing))

    questions = _questions_for_request(db, request, user.id)
    plan = AssignmentPlan(
        teacher_user_id=user.id,
        class_id=request.class_id,
        idempotency_key=request.idempotency_key,
        request_fingerprint=fingerprint,
        title=request.title.strip(),
        description=request.description,
        subject=request.subject,
        grade=request.grade,
        assignment_date=request.assignment_date,
        due_at=request.due_at,
        target_knowledge_points_json=request.target_knowledge_points,
        question_types_json=request.question_types,
        requested_question_count=request.question_count_per_tier,
        difficulty=request.difficulty,
        duration_minutes=request.duration_minutes,
        tier_strategy_json=request.tier_strategy,
        source_mode="MANUAL",
        source_provider=PROVIDER_NAME,
        source_version=PROVIDER_VERSION,
        status="DRAFT",
    )
    db.add(plan)
    try:
        db.flush()
        _replace_questions(db, plan, questions)
        reservation_id = db.info.get('014_practice_reservation_id')
        if reservation_id is not None:
            from models.learning_advice import PracticeRecommendation
            reservation = db.get(PracticeRecommendation, reservation_id)
            if reservation is None or reservation.teacher_id != user.id or reservation.class_id != plan.class_id or reservation.subject != plan.subject:
                raise HTTPException(409, detail="专项训练目标范围与计划不一致")
            reservation.plan_id = plan.id
        db.commit()
        db.refresh(plan)
    except IntegrityError:
        db.rollback()
        concurrent = db.query(AssignmentPlan).filter_by(
            teacher_user_id=user.id, idempotency_key=request.idempotency_key
        ).first()
        if concurrent is None:
            raise
        if concurrent.request_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="幂等键已用于另一份计划")
        return APIResponse(data=_plan_payload(db, concurrent))
    except Exception:
        db.rollback()
        raise
    return APIResponse(data=_plan_payload(db, plan))


@router.get("/{plan_id}", response_model=APIResponse)
def get_assignment_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    plan = _owned_plan(db, user, plan_id)
    return APIResponse(data=_plan_payload(db, plan))


@router.put("/{plan_id}", response_model=APIResponse)
def update_assignment_plan(
    plan_id: int,
    request: AssignmentPlanCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    plan = _owned_plan(db, user, plan_id, lock=True)
    from models.learning_advice import PracticeRecommendation
    if db.query(PracticeRecommendation.id).filter_by(plan_id=plan.id).first():
        raise HTTPException(409, detail="专项训练请在学科建议页核对或重新选题，不能修改其学生范围与学科")
    if plan.status != "DRAFT" or plan.assignment_id is not None:
        raise HTTPException(status_code=409, detail="只有未确认的草稿计划可以修改")
    if request.idempotency_key != plan.idempotency_key:
        raise HTTPException(status_code=409, detail="修改计划时必须保留原幂等键")
    classroom = _teacher_subject_class(db, user, request.class_id, request.subject)
    _validate_class_grade(classroom, request.grade)
    questions = _questions_for_request(db, request, user.id)
    for key, value in {
        "class_id": request.class_id,
        "request_fingerprint": _request_fingerprint(request),
        "title": request.title.strip(),
        "description": request.description,
        "subject": request.subject,
        "grade": request.grade,
        "assignment_date": request.assignment_date,
        "due_at": request.due_at,
        "target_knowledge_points_json": request.target_knowledge_points,
        "question_types_json": request.question_types,
        "requested_question_count": request.question_count_per_tier,
        "difficulty": request.difficulty,
        "duration_minutes": request.duration_minutes,
        "tier_strategy_json": request.tier_strategy,
    }.items():
        setattr(plan, key, value)
    _replace_questions(db, plan, questions)
    db.commit()
    db.refresh(plan)
    return APIResponse(data=_plan_payload(db, plan))


@router.get("/{plan_id}/variants/{level}/print.pdf")
def preview_assignment_plan_pdf(
    plan_id: int,
    level: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    plan = _owned_plan(db, user, plan_id)
    normalized = level.upper()
    if normalized not in LEVELS:
        raise HTTPException(status_code=404, detail="版本不存在")
    rows = db.query(AssignmentPlanQuestion).filter_by(plan_id=plan.id, level=normalized).order_by(
        AssignmentPlanQuestion.sort_order
    ).all()
    if not rows:
        raise HTTPException(status_code=409, detail="当前版本没有可打印题目")
    assignment = SimpleNamespace(title=plan.title, subject=plan.subject, grade=plan.grade, id=plan.id)
    variant = SimpleNamespace(level=normalized, version=1)
    questions = [SimpleNamespace(
        question_text=row.question_snapshot_json["question_text"],
        options_json=row.question_snapshot_json.get("options"),
        max_score=row.max_score,
    ) for row in rows]
    from fastapi import Response

    content = _variant_pdf(assignment, variant, questions)
    return Response(content=content, media_type="application/pdf", headers={
        "Content-Disposition": 'attachment; filename="practice-preview.pdf"'
    })


@router.post("/{plan_id}/confirm", response_model=APIResponse)
def confirm_assignment_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    plan = _owned_plan(db, user, plan_id, lock=True)
    from services.learning_advice import guard_practice_plan
    guard_practice_plan(db, plan)
    if plan.status in {"CONFIRMED", "PUBLISHED"}:
        return APIResponse(data=_plan_payload(db, plan))
    if plan.status != "DRAFT":
        raise HTTPException(status_code=409, detail="当前计划状态不能确认")
    rows = db.query(AssignmentPlanQuestion).filter_by(plan_id=plan.id).all()
    counts = {level: sum(row.level == level for row in rows) for level in LEVELS}
    if any(counts[level] != plan.requested_question_count for level in LEVELS):
        raise HTTPException(status_code=409, detail="三层版本不齐或题数不一致，不能确认")
    assets = db.query(QuestionAsset).filter(
        QuestionAsset.id.in_({row.source_asset_id for row in rows})
    ).all()
    if len(assets) != len({row.source_asset_id for row in rows}):
        raise HTTPException(status_code=409, detail="计划中的题目资产已缺失")
    for asset in assets:
        snapshot = _asset_snapshot(asset)
        if snapshot["subject"] != plan.subject or snapshot["grade"] != plan.grade:
            raise HTTPException(status_code=409, detail="题目资产已变更，计划学科或年级校验失败")
    for asset in assets:
        asset.review_status = "CONFIRMED"
    plan.status = "CONFIRMED"
    plan.confirmed_by = user.id
    plan.confirmed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(plan)
    return APIResponse(data=_plan_payload(db, plan))


@router.post("/{plan_id}/publish", response_model=APIResponse)
def publish_assignment_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    plan = _owned_plan(db, user, plan_id, lock=True)
    if plan.status == "PUBLISHED" and plan.assignment_id is not None:
        return APIResponse(data={"plan": _plan_payload(db, plan), "assignment_id": plan.assignment_id,
                                 "already_published": True})
    if plan.status != "CONFIRMED" or plan.assignment_id is not None:
        raise HTTPException(status_code=409, detail="必须先由教师确认完整计划，再发布作业")
    from services.learning_advice import guard_practice_plan
    practice = guard_practice_plan(db, plan, publishing=True)
    if practice:
        from models.classroom import StudentRoster
        valid = {r[0] for r in db.query(StudentRoster.student_id).filter(
            StudentRoster.class_id==plan.class_id,StudentRoster.status=='active',
            StudentRoster.student_id.in_(practice.target_student_ids)).all()}
        if valid!=set(practice.target_student_ids):
            raise HTTPException(409, detail="专项训练目标学生名册已变化")

    rows = db.query(AssignmentPlanQuestion).filter_by(plan_id=plan.id).order_by(
        AssignmentPlanQuestion.level, AssignmentPlanQuestion.sort_order
    ).all()
    counts = {level: sum(row.level == level for row in rows) for level in LEVELS}
    if any(counts[level] != plan.requested_question_count for level in LEVELS):
        raise HTTPException(status_code=409, detail="三层版本不齐或题数不一致，不能发布")
    assets = db.query(QuestionAsset).filter(
        QuestionAsset.id.in_({row.source_asset_id for row in rows})
    ).all()
    if len(assets) != len({row.source_asset_id for row in rows}) or any(
        item.review_status != "CONFIRMED" or item.rights_basis not in RIGHTS_BASES
        or not (item.rights_reference or "").strip()
        for item in assets
    ):
        raise HTTPException(status_code=409, detail="存在未确认或来源许可不完整的题目，不能发布")

    assignment = Assignment(
        class_id=plan.class_id,
        teacher_id=user.id,
        title=plan.title,
        description=plan.description,
        subject=plan.subject,
        grade=plan.grade,
        assignment_date=plan.assignment_date,
        due_at=plan.due_at,
        status="published",
    )
    db.add(assignment)
    db.flush()
    db.add(AssignmentVariantSet(
        assignment_id=assignment.id,
        allow_uniform_fallback=False,
        fallback_level=None,
        updated_by=user.id,
    ))
    for level in LEVELS:
        variant = AssignmentVariant(
            assignment_id=assignment.id,
            level=level,
            version=1,
            is_current=True,
            updated_by=user.id,
        )
        db.add(variant)
        db.flush()
        for row in (item for item in rows if item.level == level):
            snapshot = row.question_snapshot_json
            db.add(AssignmentVariantQuestion(
                variant_id=variant.id,
                source_type="ASSET",
                source_asset_id=row.source_asset_id,
                sort_order=row.sort_order,
                question_text=snapshot["question_text"],
                options_json=snapshot.get("options"),
                correct_answer=snapshot["correct_answer"],
                analysis=snapshot["analysis"],
                max_score=row.max_score,
            ))
    plan.assignment_id = assignment.id
    if practice:
        practice.assignment_id = assignment.id
        practice.status = "PUBLISHED"
    plan.status = "PUBLISHED"
    plan.published_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(plan)
    return APIResponse(data={"plan": _plan_payload(db, plan), "assignment_id": assignment.id,
                             "already_published": False})
