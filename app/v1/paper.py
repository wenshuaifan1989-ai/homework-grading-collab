"""011 paper-question assets, student-scoped mistakes, and correction history."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from config import settings
from models.classroom import Assignment, Class, StudentRoster
from models.homework import GradingResult, HomeworkImage, HomeworkTask, OCRResult, QuestionBlock
from models.identity_relations import ClassTeacher, Student, StudentUserBinding
from models.paper import (
    MistakeRecord,
    PaperCorrectionAttempt,
    QuestionAsset,
    QuestionAssetSource,
    QuestionDigitizationRun,
)
from models.user import User
from schemas.common import APIResponse
from schemas.paper import CorrectionReview, CorrectionSubmission, MasterySubmission, QuestionAssetReview
from services.paper_digitization import LocalWhitespacePaperDigitizeProvider, paper_digitize_provider
from services.storage_provider import COS_LOCATOR_PREFIX, get_cos_provider, get_storage_provider, materialize_image
from services.task_service import task_service
from services.identity_relations import user_has_role
from utils.database import get_db
from utils.deps import get_current_user


router = APIRouter(prefix="/paper", tags=["纸质题电子化与错题集"])
AUTO_WRONG_CONFIDENCE = 0.85


def _require_feature() -> None:
    if not settings.ENABLE_PAPER_DIGITIZATION:
        raise HTTPException(status_code=503, detail="纸质题功能尚未启用")


def _teacher_task(db: Session, user: User, task_id: str) -> tuple[HomeworkTask, Assignment]:
    if not user_has_role(db, user, "teacher"):
        raise HTTPException(status_code=404, detail="任务不存在")
    task = task_service.get_task_by_id(db, task_id)
    if task is None or task.assignment_id is None or task.class_id is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    assignment = db.query(Assignment).filter(Assignment.id == task.assignment_id).first()
    classroom = db.query(Class).filter(Class.id == task.class_id).first()
    if assignment is None or classroom is None or assignment.class_id != task.class_id:
        raise HTTPException(status_code=404, detail="任务不存在")
    member = db.query(ClassTeacher.id).filter(
        ClassTeacher.class_id == task.class_id,
        ClassTeacher.teacher_user_id == user.id,
        ClassTeacher.status == "active",
    ).first()
    any_relations = db.query(ClassTeacher.id).filter(
        ClassTeacher.class_id == task.class_id
    ).first()
    if member is None and (any_relations is not None or classroom.teacher_id != user.id):
        raise HTTPException(status_code=404, detail="任务不存在")
    return task, assignment


def _is_bound_student(db: Session, user: User, student_id: int) -> bool:
    return db.query(StudentUserBinding.id).filter(
        StudentUserBinding.user_id == user.id,
        StudentUserBinding.student_id == student_id,
        StudentUserBinding.status == "active",
    ).first() is not None


def _require_student_binding(db: Session, user: User, student_id: int) -> None:
    # Do not treat platform_admin, login User, or a shared household account as a Student.
    if not _is_bound_student(db, user, student_id):
        raise HTTPException(status_code=404, detail="错题记录不存在")


def _bbox_valid(bbox: tuple[int, int, int, int], width: int, height: int) -> bool:
    x1, y1, x2, y2 = bbox
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        return False
    if (x1, y1, x2, y2) == (0, 0, width, height):
        return False
    return ((x2 - x1) * (y2 - y1)) / float(width * height) < 0.95


def _bbox_fingerprint(image_id: int, page_index: int, bbox: tuple[int, int, int, int]) -> str:
    raw = f"{image_id}:{page_index}:{bbox[0]}:{bbox[1]}:{bbox[2]}:{bbox[3]}"
    return hashlib.sha256(raw.encode("ascii")).hexdigest()


def _question_fingerprint(asset: QuestionAsset) -> str | None:
    text = " ".join((asset.question_text or "").split()).casefold()
    if not text:
        return None
    normalized = {
        "subject": asset.subject.strip().casefold(),
        "grade": asset.grade.strip().casefold(),
        "text": text,
        "type": (asset.question_type or "").strip().casefold(),
        "options": asset.options_json,
    }
    encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _result_for_page(db: Session, task_id: str, page_index: int) -> list[tuple[GradingResult, QuestionBlock]]:
    return (
        db.query(GradingResult, QuestionBlock)
        .join(QuestionBlock, QuestionBlock.id == GradingResult.question_block_id)
        .filter(GradingResult.task_id == task_id, QuestionBlock.image_index == page_index)
        .order_by(QuestionBlock.id, GradingResult.id)
        .all()
    )


def _ocr_for_block(db: Session, task_id: str, block_id: int) -> OCRResult | None:
    return db.query(OCRResult).filter(
        OCRResult.task_id == task_id,
        OCRResult.question_block_id == block_id,
    ).order_by(OCRResult.id.desc()).first()


def _source_payload(db: Session, source: QuestionAssetSource) -> dict:
    asset = db.query(QuestionAsset).filter(QuestionAsset.id == source.question_asset_id).first()
    grading = (
        db.query(GradingResult).filter(GradingResult.id == source.grading_result_id).first()
        if source.grading_result_id is not None else None
    )
    return {
        "source_id": source.id,
        "asset_id": source.question_asset_id,
        "source_task_id": source.source_task_id,
        "source_image_id": source.source_image_id,
        "page_index": source.page_index,
        "question_no": source.question_no,
        "bbox": {"x1": source.x1, "y1": source.y1, "x2": source.x2, "y2": source.y2},
        "provider": source.provider_name,
        "provider_version": source.provider_version,
        "link_status": source.link_status,
        "review_status": source.review_status,
        "crop_url": f"/api/v1/paper/sources/{source.id}/image?kind=crop",
        "original_url": f"/api/v1/paper/sources/{source.id}/image?kind=original",
        "question": _asset_payload(asset),
        "grading_result": _grading_payload(grading) if grading else None,
    }


def _asset_payload(asset: QuestionAsset | None) -> dict | None:
    if asset is None:
        return None
    return {
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
        "confidence": float(asset.confidence) if asset.confidence is not None else None,
        "review_status": asset.review_status,
        "clean_image_status": asset.clean_image_status,
        "asset_version": asset.asset_version,
    }


def _grading_payload(grading: GradingResult) -> dict:
    block = grading.question_block
    return {
        "id": grading.id,
        "question_no": grading.question_no,
        "result": grading.result,
        "score": float(grading.reviewed_score if grading.is_reviewed and grading.reviewed_score is not None else grading.score),
        "max_score": float(grading.max_score),
        "confidence": float(grading.confidence) if grading.confidence is not None else None,
        "error_type": grading.error_type,
        "knowledge_points": grading.knowledge_points or [],
        "image_index": block.image_index if block else None,
    }


def _authorized_mistake(db: Session, user: User, mistake_id: int) -> MistakeRecord:
    mistake = db.query(MistakeRecord).filter(MistakeRecord.id == mistake_id).first()
    if mistake is None or mistake.status == "not_wrong":
        raise HTTPException(status_code=404, detail="错题记录不存在")
    if _is_bound_student(db, user, mistake.student_id):
        return mistake
    task = task_service.get_task_by_id(db, mistake.source_task_id)
    if task is not None:
        try:
            _teacher_task(db, user, task.task_id)
            return mistake
        except HTTPException:
            pass
    raise HTTPException(status_code=404, detail="错题记录不存在")


def _source_access(db: Session, user: User, source: QuestionAssetSource) -> HomeworkTask:
    task = task_service.get_task_by_id(db, source.source_task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="题目来源不存在")
    if task.student_id is not None and _is_bound_student(db, user, task.student_id):
        return task
    try:
        _teacher_task(db, user, task.task_id)
        return task
    except HTTPException:
        raise HTTPException(status_code=404, detail="题目来源不存在")


def _file_response(locator: str) -> FileResponse:
    if locator.startswith(COS_LOCATOR_PREFIX):
        handle, local_path = tempfile.mkstemp(prefix="paper-evidence-")
        os.close(handle)
        try:
            get_cos_provider().download_to(locator, local_path)
        except Exception:
            try:
                os.remove(local_path)
            except FileNotFoundError:
                pass
            raise HTTPException(status_code=502, detail="题目图片暂时无法读取")
        media_type = mimetypes.guess_type(locator)[0] or "image/jpeg"
        return FileResponse(local_path, media_type=media_type, background=BackgroundTask(os.remove, local_path))
    if not os.path.isfile(locator):
        raise HTTPException(status_code=404, detail="题目图片不存在")
    return FileResponse(locator, media_type=mimetypes.guess_type(locator)[0] or "image/jpeg")


@router.post("/tasks/{task_id}/digitize", response_model=APIResponse)
def digitize_task(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_feature()
    task, _assignment = _teacher_task(db, user, task_id)
    if task.status != "SUCCESS":
        raise HTTPException(status_code=409, detail="批改尚未成功，暂不能生成逐题候选")
    images = task_service.list_task_images(db, task_id)
    if not images:
        raise HTTPException(status_code=409, detail="作业没有可用原图")

    provider = paper_digitize_provider
    all_sources: list[QuestionAssetSource] = []
    run_summaries: list[dict] = []
    for image in images:
        page_index = int(image.image_index)
        run = db.query(QuestionDigitizationRun).filter(
            QuestionDigitizationRun.source_image_id == image.id,
            QuestionDigitizationRun.provider_version == provider.version,
        ).first()
        if run is None:
            run = QuestionDigitizationRun(
                source_task_id=task_id,
                source_image_id=image.id,
                page_index=page_index,
                provider_name=provider.name,
                provider_version=provider.version,
                status="PROCESSING",
                candidate_count=0,
            )
            db.add(run)
            db.flush()

        page_created = 0
        failure_reason = None
        try:
            with materialize_image(image.original_url) as local_image:
                from PIL import Image, ImageOps

                with Image.open(local_image) as opened:
                    oriented = ImageOps.exif_transpose(opened)
                    width, height = oriented.size
                grading_rows = _result_for_page(db, task_id, page_index)
                # Trust real OCR coordinates only; the old Vision virtual 100x80
                # full-page placeholders are deliberately rejected.
                regions = []
                ocr_blocks = db.query(QuestionBlock).filter(
                    QuestionBlock.task_id == task_id,
                    QuestionBlock.image_index == page_index,
                ).order_by(QuestionBlock.id).all()
                for block in ocr_blocks:
                    bbox = (int(block.x1), int(block.y1), int(block.x2), int(block.y2))
                    # G2 Vision's legacy placeholder is always (0,0,100,80).
                    if bbox == (0, 0, 100, 80) or not _bbox_valid(bbox, width, height):
                        continue
                    regions.append({
                        "x1": bbox[0], "y1": bbox[1], "x2": bbox[2], "y2": bbox[3],
                        "question_no": block.question_no, "confidence": None,
                    })
                if not regions:
                    regions = provider.locate_regions(local_image)
                if not regions:
                    raise ValueError("no stable ink bands; original page retained for manual review")

                for region_index, region in enumerate(regions, start=1):
                    region_data = region.as_dict() if hasattr(region, "as_dict") else dict(region)
                    bbox = tuple(int(region_data[key]) for key in ("x1", "y1", "x2", "y2"))
                    if not _bbox_valid(bbox, width, height):
                        continue
                    bbox_hash = _bbox_fingerprint(image.id, page_index, bbox)
                    source = db.query(QuestionAssetSource).filter(
                        QuestionAssetSource.source_task_id == task_id,
                        QuestionAssetSource.source_image_id == image.id,
                        QuestionAssetSource.page_index == page_index,
                        QuestionAssetSource.bbox_fingerprint == bbox_hash,
                    ).first()
                    if source is not None:
                        all_sources.append(source)
                        continue

                    linked_result = None
                    linked_block = None
                    question_no = region_data.get("question_no")
                    # Match only an explicit question number from a trusted OCR
                    # block. Whitespace-only candidates stay unlinked for teacher selection.
                    if question_no:
                        matches = [
                            (result, block) for result, block in grading_rows
                            if str(block.question_no) == str(question_no)
                        ]
                        # Duplicate question numbers on one page are ambiguous:
                        # preserve the candidate and require explicit teacher mapping.
                        pair = matches[0] if len(matches) == 1 else None
                        if pair is not None:
                            linked_result, linked_block = pair
                    crop = provider.crop_jpeg(local_image, bbox)
                    locator = get_storage_provider().store_bytes(
                        crop,
                        task_id=task_id,
                        image_index=page_index,
                        filename=f"question-{region_index}.jpg",
                        content_type="image/jpeg",
                    )
                    ocr = _ocr_for_block(db, task_id, linked_block.id) if linked_block else None
                    asset = QuestionAsset(
                        subject=task.subject,
                        grade=task.grade,
                        question_text=(ocr.question_text if ocr and ocr.question_text else None),
                        question_type=(ocr.question_type if ocr else None),
                        correct_answer=(linked_result.correct_answer if linked_result else None),
                        analysis=(linked_result.analysis if linked_result else None),
                        difficulty=(linked_result.difficulty if linked_result else None),
                        knowledge_points_json=(linked_result.knowledge_points if linked_result else None),
                        confidence=(linked_result.confidence if linked_result else None),
                        source="grading_result" if linked_result else "paper_digitization",
                        asset_version="011-v1",
                        review_status="PENDING_REVIEW",
                        clean_image_status="PENDING_REVIEW",
                    )
                    db.add(asset)
                    db.flush()
                    source = QuestionAssetSource(
                        question_asset_id=asset.id,
                        source_task_id=task_id,
                        source_image_id=image.id,
                        grading_result_id=linked_result.id if linked_result else None,
                        page_index=page_index,
                        question_no=(str(question_no) if question_no else None),
                        x1=bbox[0], y1=bbox[1], x2=bbox[2], y2=bbox[3],
                        bbox_fingerprint=bbox_hash,
                        crop_locator=locator,
                        provider_name=("existing_ocr" if question_no else provider.name),
                        provider_version=("ocr-coordinate-v1" if question_no else provider.version),
                        link_status="PENDING_REVIEW" if linked_result else "UNLINKED",
                        review_status="PENDING_REVIEW",
                        link_confidence=(linked_result.confidence if linked_result else None),
                    )
                    db.add(source)
                    db.flush()
                    all_sources.append(source)
                    page_created += 1

            run.status = "CANDIDATES_READY" if page_created else "CANDIDATES_REUSED"
            run.candidate_count = db.query(QuestionAssetSource.id).filter(
                QuestionAssetSource.source_image_id == image.id
            ).count()
            run.failure_reason = None
            db.commit()
        except Exception as exc:
            db.rollback()
            # Re-fetch/upsert after rollback so a page-level failure itself is visible.
            run = db.query(QuestionDigitizationRun).filter(
                QuestionDigitizationRun.source_image_id == image.id,
                QuestionDigitizationRun.provider_version == provider.version,
            ).first()
            if run is None:
                run = QuestionDigitizationRun(
                    source_task_id=task_id,
                    source_image_id=image.id,
                    page_index=page_index,
                    provider_name=provider.name,
                    provider_version=provider.version,
                    status="NEEDS_MANUAL_REVIEW",
                    candidate_count=0,
                )
                db.add(run)
            run.status = "NEEDS_MANUAL_REVIEW"
            run.candidate_count = 0
            run.failure_reason = type(exc).__name__
            db.commit()
            failure_reason = type(exc).__name__
        run_summaries.append({
            "source_image_id": image.id,
            "page_index": page_index,
            "status": run.status,
            "candidate_count": run.candidate_count,
            "failure_reason": failure_reason,
        })

    sources = (
        db.query(QuestionAssetSource)
        .filter(QuestionAssetSource.source_task_id == task_id)
        .order_by(QuestionAssetSource.page_index, QuestionAssetSource.y1, QuestionAssetSource.id)
        .all()
    )
    return APIResponse(data={
        "task_id": task_id,
        "provider": provider.name,
        "provider_version": provider.version,
        "runs": run_summaries,
        "sources": [_source_payload(db, source) for source in sources],
        "accuracy_status": "PENDING_REVIEW",
    })


@router.get("/tasks/{task_id}/assets", response_model=APIResponse)
def list_task_assets(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_feature()
    task, _assignment = _teacher_task(db, user, task_id)
    sources = (
        db.query(QuestionAssetSource)
        .filter(QuestionAssetSource.source_task_id == task.task_id)
        .order_by(QuestionAssetSource.page_index, QuestionAssetSource.y1, QuestionAssetSource.id)
        .all()
    )
    grading_rows = (
        db.query(GradingResult, QuestionBlock)
        .join(QuestionBlock, QuestionBlock.id == GradingResult.question_block_id)
        .filter(GradingResult.task_id == task_id)
        .order_by(QuestionBlock.image_index, QuestionBlock.id)
        .all()
    )
    results = []
    for grading, block in grading_rows:
        ocr = _ocr_for_block(db, task_id, block.id)
        result = _grading_payload(grading)
        result["question_text"] = ocr.question_text if ocr else None
        result["question_type"] = ocr.question_type if ocr else None
        result["student_answer"] = ocr.student_answer if ocr else None
        result["correct_answer"] = grading.correct_answer
        result["analysis"] = grading.analysis
        results.append(result)
    return APIResponse(data={
        "task_id": task_id,
        "status": task.status,
        "sources": [_source_payload(db, source) for source in sources],
        "grading_results": results,
        "accuracy_status": "PENDING_REVIEW",
    })


@router.patch("/sources/{source_id}/review", response_model=APIResponse)
def review_source(
    source_id: int,
    request: QuestionAssetReview,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_feature()
    source = db.query(QuestionAssetSource).filter(QuestionAssetSource.id == source_id).first()
    if source is None:
        raise HTTPException(status_code=404, detail="题目候选不存在")
    task, assignment = _teacher_task(db, user, source.source_task_id)
    image = db.query(HomeworkImage).filter(
        HomeworkImage.id == source.source_image_id,
        HomeworkImage.task_id == task.task_id,
    ).first()
    grading = db.query(GradingResult).filter(
        GradingResult.id == request.grading_result_id,
        GradingResult.task_id == task.task_id,
    ).first()
    if image is None or grading is None:
        raise HTTPException(status_code=422, detail="批改结果与原图来源不匹配")
    block = db.query(QuestionBlock).filter(
        QuestionBlock.id == grading.question_block_id,
        QuestionBlock.task_id == task.task_id,
    ).first()
    if block is None or int(block.image_index) != int(source.page_index):
        raise HTTPException(status_code=422, detail="批改题目不属于当前来源页")
    duplicate_link = db.query(QuestionAssetSource.id).filter(
        QuestionAssetSource.grading_result_id == grading.id,
        QuestionAssetSource.id != source.id,
    ).first()
    if duplicate_link:
        raise HTTPException(status_code=409, detail="该批改题已关联到另一题目候选")

    bbox_values = (request.x1, request.y1, request.x2, request.y2)
    if any(value is not None for value in bbox_values):
        if any(value is None for value in bbox_values):
            raise HTTPException(status_code=422, detail="边界框需同时提供 x1/y1/x2/y2")
        bbox = tuple(int(value) for value in bbox_values)
    else:
        bbox = (source.x1, source.y1, source.x2, source.y2)
    with materialize_image(image.original_url) as local_image:
        from PIL import Image, ImageOps

        with Image.open(local_image) as opened:
            width, height = ImageOps.exif_transpose(opened).size
        if not _bbox_valid(bbox, width, height):
            raise HTTPException(status_code=422, detail="边界框越界、为空或覆盖整页，未保存")
        new_bbox_hash = _bbox_fingerprint(image.id, source.page_index, bbox)
        duplicate_bbox = db.query(QuestionAssetSource.id).filter(
            QuestionAssetSource.source_task_id == task.task_id,
            QuestionAssetSource.source_image_id == image.id,
            QuestionAssetSource.page_index == source.page_index,
            QuestionAssetSource.bbox_fingerprint == new_bbox_hash,
            QuestionAssetSource.id != source.id,
        ).first()
        if duplicate_bbox:
            raise HTTPException(status_code=409, detail="该边界框已存在候选")
        if bbox != (source.x1, source.y1, source.x2, source.y2):
            crop = paper_digitize_provider.crop_jpeg(local_image, bbox)
            source.crop_locator = get_storage_provider().store_bytes(
                crop,
                task_id=task.task_id,
                image_index=source.page_index,
                filename=f"question-review-{source.id}.jpg",
                content_type="image/jpeg",
            )
            source.x1, source.y1, source.x2, source.y2 = bbox
            source.bbox_fingerprint = new_bbox_hash

    ocr = _ocr_for_block(db, task.task_id, block.id)
    question_text = request.question_text.strip() or (ocr.question_text.strip() if ocr and ocr.question_text else "")
    if request.confirm and not question_text:
        raise HTTPException(status_code=422, detail="题干尚未校对，不能确认发布")
    asset = db.query(QuestionAsset).filter(QuestionAsset.id == source.question_asset_id).first()
    if asset is None:
        raise HTTPException(status_code=409, detail="题目资产缺失，需重新生成候选")
    asset.subject = task.subject
    asset.grade = task.grade
    asset.question_text = question_text or None
    asset.question_type = request.question_type or (ocr.question_type if ocr else None)
    asset.options_json = request.options
    asset.correct_answer = request.correct_answer or grading.correct_answer
    asset.analysis = request.analysis or grading.analysis
    asset.difficulty = request.difficulty or grading.difficulty
    asset.knowledge_points_json = request.knowledge_points or grading.knowledge_points or []
    asset.confidence = grading.confidence
    fingerprint = _question_fingerprint(asset) if request.confirm else None
    if fingerprint:
        canonical = db.query(QuestionAsset).filter(
            QuestionAsset.content_fingerprint == fingerprint,
            QuestionAsset.review_status == "CONFIRMED",
            QuestionAsset.id != asset.id,
        ).first()
        if canonical:
            source.question_asset_id = canonical.id
            db.flush()
            db.delete(asset)
            asset = canonical
        else:
            asset.content_fingerprint = fingerprint
            asset.review_status = "CONFIRMED"
    else:
        asset.review_status = "PENDING_REVIEW"
    source.grading_result_id = grading.id
    source.question_no = request.question_no or grading.question_no
    source.link_status = "CONFIRMED" if request.confirm else "PENDING_REVIEW"
    source.review_status = "CONFIRMED" if request.confirm else "PENDING_REVIEW"
    source.reviewed_by = user.id
    source.reviewed_at = datetime.utcnow() if request.confirm else None
    db.flush()

    mistake_created = False
    reason = None
    wrong_is_confirmed = request.manual_wrong is True or (
        request.manual_wrong is None
        and grading.result == "wrong"
        and grading.confidence is not None
        and float(grading.confidence) >= AUTO_WRONG_CONFIDENCE
    )
    existing_mistake = db.query(MistakeRecord).filter(
        MistakeRecord.student_id == task.student_id,
        MistakeRecord.source_grading_result_id == grading.id,
    ).first() if task.student_id is not None else None
    result_mistake_id = existing_mistake.id if existing_mistake else None
    if request.manual_wrong is False and existing_mistake is not None:
        existing_mistake.status = "not_wrong"
        result_mistake_id = None
        reason = "teacher_marked_not_wrong"
    elif request.confirm and wrong_is_confirmed and task.student_id is not None:
        roster = db.query(StudentRoster.id).filter(
            StudentRoster.class_id == assignment.class_id,
            StudentRoster.student_id == task.student_id,
            StudentRoster.status == "active",
        ).first()
        if roster is None:
            reason = "student_not_in_active_assignment_class"
        elif existing_mistake is None:
            new_mistake = MistakeRecord(
                student_id=task.student_id,
                assignment_id=assignment.id,
                question_asset_id=asset.id,
                question_asset_source_id=source.id,
                source_task_id=task.task_id,
                source_grading_result_id=grading.id,
                detection_basis=("teacher_confirmed" if request.manual_wrong is True else "high_confidence_model"),
                status="open",
            )
            db.add(new_mistake)
            db.flush()
            result_mistake_id = new_mistake.id
            mistake_created = True
        else:
            existing_mistake.question_asset_id = asset.id
            existing_mistake.question_asset_source_id = source.id
            existing_mistake.last_seen_at = datetime.utcnow()
            existing_mistake.status = "open"
            result_mistake_id = existing_mistake.id
            mistake_created = True
    elif grading.result == "wrong" and (grading.confidence is None or float(grading.confidence) < AUTO_WRONG_CONFIDENCE):
        reason = "low_or_missing_confidence_requires_teacher_confirmation"
    elif task.student_id is None:
        reason = "homework_has_no_student_entity"

    db.commit()
    return APIResponse(data={
        "source": _source_payload(db, source),
        "mistake_created": mistake_created,
        "mistake_id": result_mistake_id,
        "mistake_status_reason": reason,
        "clean_image_status": asset.clean_image_status,
    })


def _mistake_query(db: Session):
    return (
        db.query(MistakeRecord)
        .join(QuestionAsset, QuestionAsset.id == MistakeRecord.question_asset_id)
        .filter(MistakeRecord.status != "not_wrong")
    )


def _mistake_payload(db: Session, mistake: MistakeRecord) -> dict:
    asset = db.query(QuestionAsset).filter(QuestionAsset.id == mistake.question_asset_id).first()
    source = db.query(QuestionAssetSource).filter(
        QuestionAssetSource.id == mistake.question_asset_source_id
    ).first()
    grading = db.query(GradingResult).filter(
        GradingResult.id == mistake.source_grading_result_id
    ).first()
    student_name = db.query(Student.name).filter(Student.id == mistake.student_id).scalar()
    assignment = db.query(Assignment).filter(Assignment.id == mistake.assignment_id).first()
    task = task_service.get_task_by_id(db, mistake.source_task_id)
    return {
        "id": mistake.id,
        "student_id": mistake.student_id,
        "student_name": student_name,
        "assignment_id": mistake.assignment_id,
        "assignment_title": assignment.title if assignment else None,
        "subject": asset.subject if asset else (task.subject if task else None),
        "question_no": source.question_no if source else (grading.question_no if grading else None),
        "knowledge_points": asset.knowledge_points_json if asset else [],
        "question": _asset_payload(asset),
        "grading_result": _grading_payload(grading) if grading else None,
        "source_task_id": mistake.source_task_id,
        "source_id": source.id if source else None,
        "source_page_index": source.page_index if source else None,
        "source_bbox": ({"x1": source.x1, "y1": source.y1, "x2": source.x2, "y2": source.y2} if source else None),
        "crop_url": f"/api/v1/paper/mistakes/{mistake.id}/image?kind=crop",
        "original_url": f"/api/v1/paper/mistakes/{mistake.id}/image?kind=original",
        "status": mistake.status,
        "detection_basis": mistake.detection_basis,
        "created_at": mistake.created_at,
    }


@router.get("/students/{student_id}/mistakes", response_model=APIResponse)
def list_student_mistakes(
    student_id: int,
    subject: str | None = Query(None, max_length=40),
    knowledge_point: str | None = Query(None, max_length=120),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_feature()
    _require_student_binding(db, user, student_id)
    query = _mistake_query(db).filter(MistakeRecord.student_id == student_id)
    if subject:
        query = query.filter(QuestionAsset.subject == subject)
    rows = query.order_by(MistakeRecord.created_at.desc(), MistakeRecord.id.desc()).all()
    if knowledge_point:
        rows = [row for row in rows if knowledge_point in (
            db.query(QuestionAsset.knowledge_points_json)
            .filter(QuestionAsset.id == row.question_asset_id).scalar() or []
        )]
    return APIResponse(data={"student_id": student_id, "items": [_mistake_payload(db, row) for row in rows]})


@router.get("/classes/{class_id}/mistakes", response_model=APIResponse)
def list_class_mistakes(
    class_id: int,
    student_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_feature()
    if not user_has_role(db, user, "teacher"):
        raise HTTPException(status_code=404, detail="班级不存在")
    classroom = db.query(Class).filter(Class.id == class_id).first()
    member = db.query(ClassTeacher.id).filter(
        ClassTeacher.class_id == class_id,
        ClassTeacher.teacher_user_id == user.id,
        ClassTeacher.status == "active",
    ).first()
    any_relation = db.query(ClassTeacher.id).filter(ClassTeacher.class_id == class_id).first()
    if classroom is None or (member is None and (any_relation is not None or classroom.teacher_id != user.id)):
        raise HTTPException(status_code=404, detail="班级不存在")
    query = _mistake_query(db).join(Assignment, Assignment.id == MistakeRecord.assignment_id).filter(
        Assignment.class_id == class_id
    )
    if student_id is not None:
        roster = db.query(StudentRoster.id).filter(
            StudentRoster.class_id == class_id,
            StudentRoster.student_id == student_id,
            StudentRoster.status == "active",
        ).first()
        if roster is None:
            raise HTTPException(status_code=404, detail="学生不属于该班级")
        query = query.filter(MistakeRecord.student_id == student_id)
    rows = query.order_by(MistakeRecord.created_at.desc(), MistakeRecord.id.desc()).all()
    return APIResponse(data={"class_id": class_id, "items": [_mistake_payload(db, row) for row in rows]})


@router.get("/mistakes/{mistake_id}", response_model=APIResponse)
def get_mistake(
    mistake_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_feature()
    mistake = _authorized_mistake(db, user, mistake_id)
    return APIResponse(data=_mistake_payload(db, mistake))


@router.get("/mistakes/{mistake_id}/history", response_model=APIResponse)
def get_correction_history(
    mistake_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_feature()
    mistake = _authorized_mistake(db, user, mistake_id)
    attempts = db.query(PaperCorrectionAttempt).filter(
        PaperCorrectionAttempt.mistake_id == mistake.id
    ).order_by(PaperCorrectionAttempt.created_at, PaperCorrectionAttempt.id).all()
    return APIResponse(data={"mistake_id": mistake.id, "items": [{
        "id": item.id,
        "attempt_type": item.attempt_type,
        "submitted_answer": item.submitted_answer,
        "note": item.note,
        "status": item.status,
        "review_feedback": item.review_feedback,
        "created_at": item.created_at,
        "reviewed_at": item.reviewed_at,
    } for item in attempts]})


@router.post("/mistakes/{mistake_id}/corrections", response_model=APIResponse)
def submit_correction(
    mistake_id: int,
    request: CorrectionSubmission,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_feature()
    mistake = db.query(MistakeRecord).filter(MistakeRecord.id == mistake_id).first()
    if mistake is None or mistake.status == "not_wrong":
        raise HTTPException(status_code=404, detail="错题记录不存在")
    _require_student_binding(db, user, mistake.student_id)
    attempt = PaperCorrectionAttempt(
        mistake_id=mistake.id,
        student_id=mistake.student_id,
        attempt_type="correction",
        submitted_answer=request.answer.strip(),
        note=request.note,
        status="submitted",
    )
    mistake.status = "correction_submitted"
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return APIResponse(data={"attempt_id": attempt.id, "mistake_id": mistake.id, "status": attempt.status})


@router.post("/mistakes/{mistake_id}/mastery", response_model=APIResponse)
def mark_mastered(
    mistake_id: int,
    request: MasterySubmission,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_feature()
    mistake = db.query(MistakeRecord).filter(MistakeRecord.id == mistake_id).first()
    if mistake is None or mistake.status == "not_wrong":
        raise HTTPException(status_code=404, detail="错题记录不存在")
    _require_student_binding(db, user, mistake.student_id)
    attempt = PaperCorrectionAttempt(
        mistake_id=mistake.id,
        student_id=mistake.student_id,
        attempt_type="mark_mastered",
        note=request.note,
        status="self_reported_mastered",
    )
    mistake.status = "mastered_self_reported"
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return APIResponse(data={"attempt_id": attempt.id, "mistake_id": mistake.id, "status": attempt.status})


@router.post("/mistakes/{mistake_id}/corrections/{attempt_id}/review", response_model=APIResponse)
def review_correction(
    mistake_id: int,
    attempt_id: int,
    request: CorrectionReview,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_feature()
    mistake = db.query(MistakeRecord).filter(MistakeRecord.id == mistake_id).first()
    attempt = db.query(PaperCorrectionAttempt).filter(
        PaperCorrectionAttempt.id == attempt_id,
        PaperCorrectionAttempt.mistake_id == mistake_id,
    ).first()
    if mistake is None or attempt is None or mistake.status == "not_wrong":
        raise HTTPException(status_code=404, detail="订正记录不存在")
    task = task_service.get_task_by_id(db, mistake.source_task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="订正记录不存在")
    _teacher_task(db, user, task.task_id)
    attempt.status = "accepted" if request.accepted else "retry_requested"
    attempt.review_feedback = request.feedback
    attempt.reviewed_by = user.id
    attempt.reviewed_at = datetime.utcnow()
    mistake.status = "mastered" if request.accepted else "open"
    db.commit()
    return APIResponse(data={"attempt_id": attempt.id, "mistake_id": mistake.id, "status": attempt.status})


def _serve_source_image(db: Session, user: User, source: QuestionAssetSource, kind: str) -> FileResponse:
    task = _source_access(db, user, source)
    if kind == "crop":
        locator = source.crop_locator
    elif kind == "original":
        image = db.query(HomeworkImage).filter(
            HomeworkImage.id == source.source_image_id,
            HomeworkImage.task_id == task.task_id,
        ).first()
        if image is None:
            raise HTTPException(status_code=404, detail="原图不存在")
        locator = image.original_url
    else:
        raise HTTPException(status_code=422, detail="kind 仅支持 crop 或 original")
    return _file_response(locator)


@router.get("/sources/{source_id}/image")
def get_source_image(
    source_id: int,
    kind: str = Query("crop"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_feature()
    source = db.query(QuestionAssetSource).filter(QuestionAssetSource.id == source_id).first()
    if source is None:
        raise HTTPException(status_code=404, detail="题目来源不存在")
    return _serve_source_image(db, user, source, kind)


@router.get("/mistakes/{mistake_id}/image")
def get_mistake_image(
    mistake_id: int,
    kind: str = Query("crop"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_feature()
    mistake = _authorized_mistake(db, user, mistake_id)
    source = db.query(QuestionAssetSource).filter(
        QuestionAssetSource.id == mistake.question_asset_source_id
    ).first()
    if source is None:
        raise HTTPException(status_code=404, detail="题目来源不存在")
    return _serve_source_image(db, user, source, kind)
