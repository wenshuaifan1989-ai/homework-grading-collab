import base64
import json
import tempfile
import re
from datetime import datetime, timedelta
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, Query, Header
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import uuid
import os
from typing import List, Optional
from utils.database import get_db
from schemas.common import APIResponse
from schemas.homework import (
    HomeworkListResponse,
    TaskStatusResponse,
    GradingResultResponse,
    HomeworkRetryRequest,
)
from services.task_service import task_service
from tasks.homework_tasks import process_homework_task, process_analyze_task
from config import settings
from utils.logger import logger
from utils.deps import get_current_user
from models.user import User
from models.classroom import Assignment, StudentRoster
from models.identity_relations import StudentUserBinding
from models.homework import HomeworkTask
from models.model_usage import ModelCallAudit
from models.submission import HomeworkSubmissionKey
from services.learning import resolve_assignment_variant
from services.identity_relations import user_can_access_student, user_role_codes
from services.storage_provider import COS_LOCATOR_PREFIX, get_cos_provider, get_storage_provider, materialize_image

router = APIRouter(prefix="/homework", tags=["作业管理"])

MAX_IMAGES_PER_TASK = 9
TASK_RECOVERY_MIN_AGE_SECONDS = 240


def _stale_recovery_cutoff(now: datetime | None = None) -> datetime:
    timeout = max(0, int(settings.VISION_REQUEST_TIMEOUT_SECONDS))
    grace = max(TASK_RECOVERY_MIN_AGE_SECONDS, timeout + 120)
    return (now or datetime.utcnow()) - timedelta(seconds=grace)


def _is_stale_vision_task(task: HomeworkTask, now: datetime | None = None) -> bool:
    return bool(
        task.grading_mode == "vision"
        and task.status in {"PROCESSING", "GRADING"}
        and task.updated_at is not None
        and task.updated_at <= _stale_recovery_cutoff(now)
    )


def _owned_task(db: Session, task_id: str, user: User):
    task = task_service.get_task_by_id(db, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


def _start_submission_key(db: Session, user_id: int, request_key: str | None, task_id: str):
    if not request_key:
        return None, None
    if not re.fullmatch(r"[A-Za-z0-9._:-]{8,64}", request_key):
        raise HTTPException(status_code=422, detail="提交幂等标识格式无效")

    record = db.query(HomeworkSubmissionKey).filter_by(
        user_id=user_id, request_key=request_key
    ).with_for_update().first()
    if record:
        existing_task = task_service.get_task_by_id(db, record.task_id)
        if existing_task:
            return record, existing_task
        age = datetime.utcnow() - record.updated_at
        if record.status == "PROCESSING" and age < timedelta(minutes=10):
            raise HTTPException(status_code=409, detail="相同提交正在接收，请稍后查看作业记录")
        record.task_id = task_id
        record.status = "PROCESSING"
        record.updated_at = datetime.utcnow()
        db.commit()
        return record, None

    record = HomeworkSubmissionKey(
        user_id=user_id,
        request_key=request_key,
        task_id=task_id,
        status="PROCESSING",
    )
    db.add(record)
    try:
        db.commit()
        db.refresh(record)
        return record, None
    except IntegrityError:
        db.rollback()
        record = db.query(HomeworkSubmissionKey).filter_by(
            user_id=user_id, request_key=request_key
        ).first()
        if record:
            existing_task = task_service.get_task_by_id(db, record.task_id)
            if existing_task:
                return record, existing_task
        raise HTTPException(status_code=409, detail="相同提交正在接收，请稍后查看作业记录")


def _complete_submission_key(db: Session, user_id: int, request_key: str | None):
    if not request_key:
        return
    record = db.query(HomeworkSubmissionKey).filter_by(
        user_id=user_id, request_key=request_key
    ).first()
    if record:
        record.status = "CREATED"
        record.updated_at = datetime.utcnow()
        db.commit()


def _fail_submission_key(db: Session, user_id: int, request_key: str | None):
    if not request_key:
        return
    # A failed flush leaves SQLAlchemy's transaction unusable; rollback first,
    # then update by key without touching an expired ORM instance.
    db.rollback()
    db.query(HomeworkSubmissionKey).filter_by(
        user_id=user_id, request_key=request_key, status="PROCESSING"
    ).update(
        {HomeworkSubmissionKey.status: "FAILED", HomeworkSubmissionKey.updated_at: datetime.utcnow()},
        synchronize_session=False,
    )
    db.commit()


def _existing_submission_response(db: Session, task: HomeworkTask):
    image_count = len(task_service.list_task_images(db, task.task_id))
    return APIResponse(data={
        "task_id": task.task_id,
        "mode": task.grading_mode,
        "status": task.status.lower(),
        "image_count": image_count,
        "assignment_id": task.assignment_id,
        "idempotent_replay": True,
    })


async def _save_upload(file: UploadFile, task_id: str, image_index: int = 0) -> tuple[str, bytes]:
    file_bytes = await file.read()
    if len(file_bytes) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="文件大小不能超过10MB")
    if not file_bytes or file.content_type not in {"image/jpeg", "image/png", "image/gif", "image/bmp"}:
        raise HTTPException(status_code=400, detail="仅支持有效的作业图片")
    try:
        from io import BytesIO
        from PIL import Image, UnidentifiedImageError

        with Image.open(BytesIO(file_bytes)) as image:
            if image.format not in {"JPEG", "PNG", "GIF", "BMP"}:
                raise ValueError("unsupported image format")
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(status_code=400, detail="仅支持有效的作业图片")
    locator = get_storage_provider().store_bytes(
        file_bytes,
        task_id=task_id,
        image_index=image_index,
        filename=file.filename,
        content_type=file.content_type,
    )
    return locator, file_bytes


# ======================== 提交作业 ========================

@router.post("/analyze", response_model=APIResponse)
async def analyze_homework(
    file: Optional[UploadFile] = File(None),
    files: Optional[List[UploadFile]] = File(None),
    subject: str = Form(...),
    grade: str = Form(...),
    model: Optional[str] = Form(None),
    mode: Optional[str] = Form(None),
    assignment_id: Optional[int] = Form(None),
    student_id: Optional[int] = Form(None),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """提交作业图片进行分析/批改

    支持单图（`file`，向后兼容）与多图（`files`，1-9 张）：
    - mode=ocr:  OCR 流水线 - 先切题返回区域供前端选择，确认后逐题识别+批改
    - mode=vision: 视觉大模型直接看图批改，一步到位

    G2：多张图片作为**同一个 HomeworkTask** 顺序批改并汇总返回。
    """
    submission_record = None
    try:
        assignment = None
        assignment_class_id = None
        homework_student_id = None
        selected_assignment_variant = None
        grading_mode = mode or settings.GRADING_MODE
        if assignment_id is not None:
            roles = user_role_codes(db, user)
            has_family_binding = db.query(StudentUserBinding.id).filter(
                StudentUserBinding.user_id == user.id,
                StudentUserBinding.status == "active",
            ).first() is not None
            if "student" not in roles and not has_family_binding:
                raise HTTPException(status_code=403, detail="只有学生或其家庭成员可以提交班级作业")
            grading_mode = mode or "vision"
            if grading_mode not in {"vision", "known"}:
                raise HTTPException(status_code=400, detail="班级作业提交必须使用 vision 或 known 模式")
            assignment = (
                db.query(Assignment)
                .filter(Assignment.id == assignment_id, Assignment.status == "published")
                .first()
            )
            if assignment is None:
                raise HTTPException(status_code=404, detail="作业不存在")
            eligible_student_ids = [
                int(row[0])
                for row in db.query(StudentRoster.student_id)
                .join(StudentUserBinding, StudentUserBinding.student_id == StudentRoster.student_id)
                .filter(
                    StudentRoster.class_id == assignment.class_id,
                    StudentRoster.status == "active",
                    StudentRoster.student_id.is_not(None),
                    StudentUserBinding.user_id == user.id,
                    StudentUserBinding.status == "active",
                )
                .distinct()
                .all()
            ]
            if student_id is None:
                has_non_self_binding = db.query(StudentUserBinding.id).filter(
                    StudentUserBinding.user_id == user.id,
                    StudentUserBinding.status == "active",
                    StudentUserBinding.relationship_type != "self",
                ).first() is not None
                if len(eligible_student_ids) == 1 and not has_non_self_binding:
                    homework_student_id = eligible_student_ids[0]
                else:
                    raise HTTPException(status_code=422, detail="请先选择本次作业所属学生")
            else:
                homework_student_id = student_id
            roster_binding = db.query(StudentRoster.id).filter(
                StudentRoster.class_id == assignment.class_id,
                StudentRoster.student_id == homework_student_id,
                StudentRoster.status == "active",
            ).first()
            if roster_binding is None or not user_can_access_student(
                db, user, homework_student_id, class_id=assignment.class_id
            ):
                raise HTTPException(status_code=403, detail="请先绑定该班级的学生身份")
            assignment_class_id = assignment.class_id
            from services.learning_advice import practice_for_assignment, can_receive_practice
            practice = practice_for_assignment(db,assignment.id)
            if not can_receive_practice(practice,homework_student_id):
                raise HTTPException(status_code=403,detail="当前学生不在本次专项训练授权范围")
            if practice is not None:
                # 014 has no paid model authorization. Missing/non-choice
                # templates remain local UNKNOWN_LAYOUT, never model fallback.
                grading_mode = "known"
            # The published assignment is authoritative for the grading subject and grade.
            subject = assignment.subject
            grade = assignment.grade
            from services.teacher_v2 import publication_for
            if publication_for(db, assignment.id):
                grading_mode = 'known'  # No implicit paid fallback for V2 originals.
            variant_set, selected_assignment_variant = resolve_assignment_variant(
                db, assignment, homework_student_id
            )
            if variant_set is not None and selected_assignment_variant is None:
                raise HTTPException(
                    status_code=409,
                    detail="老师尚未为当前学生准备好该作业版本，请联系老师后再提交",
                )
            # Any registered template (even draft/stale) opts this variant into
            # local handling. Missing/stale mapping becomes UNKNOWN_LAYOUT,
            # never an implicit paid fallback. Variant is server-resolved.
            if selected_assignment_variant is not None:
                from models.known_assignment import PageTemplate
                if db.query(PageTemplate.id).filter_by(assignment_id=assignment.id).first():
                    grading_mode = "known"
        else:
            if grading_mode == "known":
                raise HTTPException(status_code=409, detail="自主拍照无已知作业模板；UNKNOWN_LAYOUT，不调用付费识别")
            accessible_ids = [int(row[0]) for row in db.query(
                StudentUserBinding.student_id
            ).filter(
                StudentUserBinding.user_id == user.id,
                StudentUserBinding.status == "active",
            ).order_by(StudentUserBinding.student_id).all()]
            if student_id is None:
                if len(accessible_ids) != 1:
                    raise HTTPException(status_code=422, detail="请先选择本次自主练习所属学生")
                homework_student_id = accessible_ids[0]
            else:
                homework_student_id = student_id
            if not user_can_access_student(db, user, homework_student_id):
                raise HTTPException(status_code=403, detail="无权为该学生创建自主练习")

        uploads: List[UploadFile] = []
        if file is not None:
            uploads.append(file)
        if files:
            uploads.extend([f for f in files if f is not None])

        if not uploads:
            raise HTTPException(status_code=400, detail="请至少上传 1 张作业图片")
        if len(uploads) > MAX_IMAGES_PER_TASK:
            raise HTTPException(
                status_code=400,
                detail=f"单个任务最多上传 {MAX_IMAGES_PER_TASK} 张图片，当前 {len(uploads)} 张",
            )

        task_id = f"task_{uuid.uuid4().hex}"
        submission_record, existing_task = _start_submission_key(
            db, user.id, idempotency_key, task_id
        )
        if existing_task:
            return _existing_submission_response(db, existing_task)

        image_paths: List[str] = []
        for image_index, upload in enumerate(uploads):
            path, _ = await _save_upload(upload, task_id, image_index)
            image_paths.append(path)

        model_name = model or (settings.text_models[0].name if settings.text_models else None)

        task_service.create_task_with_images(
            db,
            task_id,
            user.id,
            subject,
            grade,
            image_paths,
            grading_mode=grading_mode,
            assignment_id=assignment.id if assignment else None,
            class_id=assignment_class_id,
            student_id=homework_student_id,
            actor_user_id=user.id,
            assignment_variant_id=(
                selected_assignment_variant.id if selected_assignment_variant else None
            ),
        )
        _complete_submission_key(db, user.id, idempotency_key)

        if grading_mode in {"vision", "known"}:
            # 视觉模式: 直接批改（多图在同一个任务内顺序处理）
            try:
                process_homework_task.delay(
                    task_id, image_paths[0], subject, grade, user.id,
                    grading_mode=grading_mode, model_name=model_name,
                )
            except Exception as queue_error:
                task_service.update_task_status(
                    db, task_id, "FAILED", "任务队列暂不可用；图片已保存，尚未调用模型"
                )
                logger.error("无法排入本地作业队列: task_id={}, error_type={}", task_id, type(queue_error).__name__)
                raise HTTPException(status_code=503, detail="作业已保存但任务队列暂不可用；请在记录页安全重试")
            return APIResponse(data={
                "task_id": task_id, "mode": grading_mode,
                "status": "processing", "image_count": len(image_paths),
                "assignment_id": assignment.id if assignment else None,
                "message": "本地括号识别已排队，不调用付费模型" if grading_mode == "known" else "视觉模型正在批改中"
            })
        else:
            # OCR 模式: 逐张切题，返回按图片顺序的区域
            from clients.aliyun_client import aliyun_ocr_client

            regions = []
            for image_index, image_locator in enumerate(image_paths):
                with materialize_image(image_locator) as image_path:
                    question_blocks = aliyun_ocr_client.recognize_edu_paper_cut(image_path)
                    task_service.save_question_blocks_raw(
                        db, task_id, question_blocks, image_path, image_index=image_index
                    )
                for i, b in enumerate(question_blocks):
                    regions.append({
                        "index": len(regions),
                        "image_index": image_index,
                        "question_no": b.get("question_no", str(i + 1)),
                        "x1": int(b.get("x1", 0)),
                        "y1": int(b.get("y1", 0)),
                        "x2": int(b.get("x2", 0)),
                        "y2": int(b.get("y2", 0)),
                        "text_preview": (b.get("text", "") or "")[:80],
                    })

            logger.info(f"切题完成: {task_id}, {len(regions)} 个区域, {len(image_paths)} 张图")
            return APIResponse(data={
                "task_id": task_id, "mode": "ocr",
                "status": "regions_ready",
                "regions": regions,
                "image_count": len(image_paths),
                "assignment_id": assignment.id if assignment else None,
                "image_url": f"/api/v1/homework/image/{task_id}",
            })

    except HTTPException:
        if submission_record is not None:
            _fail_submission_key(db, user.id, idempotency_key)
        raise
    except Exception as e:
        logger.opt(exception=True).error("提交失败: {}", str(e))
        if submission_record is not None:
            _fail_submission_key(db, user.id, idempotency_key)
        raise HTTPException(status_code=500, detail="提交失败")


# ======================== 切题区域 ========================

@router.get("/regions/{task_id}", response_model=APIResponse)
def get_regions(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取切题区域信息，包含裁剪后的小图 base64 预览"""
    try:
        _owned_task(db, task_id, user)

        from models.homework import QuestionBlock
        blocks = (
            db.query(QuestionBlock)
            .filter(QuestionBlock.task_id == task_id)
            .order_by(QuestionBlock.id)
            .all()
        )

        if not blocks:
            raise HTTPException(status_code=404, detail="该任务无切题数据，请先提交分析")

        regions = []
        for i, b in enumerate(blocks):
            preview_b64 = None
            if b.question_image_url and os.path.exists(b.question_image_url):
                with open(b.question_image_url, "rb") as f:
                    preview_b64 = base64.b64encode(f.read()).decode("utf-8")

            regions.append({
                "block_id": b.id,
                "index": i,
                "question_no": b.question_no,
                "x1": b.x1, "y1": b.y1, "x2": b.x2, "y2": b.y2,
                "preview_base64": preview_b64,
            })

        return APIResponse(data={
            "task_id": task_id,
            "regions": regions,
            "region_count": len(regions),
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.opt(exception=True).error("获取区域失败: {}", str(e))
        raise HTTPException(status_code=500, detail="获取区域失败")


# ======================== 确认并批改 ========================

@router.post("/{task_id}/confirm", response_model=APIResponse)
async def confirm_and_grade(
    task_id: str,
    model: Optional[str] = Form(None),
    selected_indices: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """确认切题区域并开始 OCR + 批改

    selected_indices: 逗号分隔的 region index (如 "0,1,3,5")，为空则使用全部区域
    """
    try:
        task = _owned_task(db, task_id, user)
        if task.assignment_id is not None:
            raise HTTPException(status_code=409, detail="班级作业不支持 OCR 确认重放")

        from models.homework import HomeworkImage, QuestionBlock
        image = db.query(HomeworkImage).filter(HomeworkImage.task_id == task_id).first()
        if not image or not image.original_url:
            raise HTTPException(status_code=400, detail="找不到原始图片")

        model_name = model or (settings.text_models[0].name if settings.text_models else None)

        # 解析选中的区域
        if selected_indices:
            indices = [int(x.strip()) for x in selected_indices.split(",") if x.strip()]
        else:
            indices = None

        process_analyze_task.delay(
            task_id, image.original_url, task.subject, task.grade, task.user_id,
            grading_mode="ocr", model_name=model_name,
            selected_indices=json.dumps(indices) if indices else "",
        )

        task_service.update_task_status(db, task_id, "PROCESSING")
        logger.info(f"确认批改: {task_id}, model={model_name}, indices={indices}")
        return APIResponse(data={
            "task_id": task_id,
            "mode": "ocr",
            "status": "processing",
            "selected_count": len(indices) if indices else "all",
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.opt(exception=True).error("确认批改失败: {}", str(e))
        raise HTTPException(status_code=500, detail="确认批改失败")


# ======================== 原图预览 ========================

@router.get("/image/{task_id}")
async def get_original_image(
    task_id: str,
    image_index: int = Query(0, ge=0, le=8),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取原始上传图片 (用于前端切题区域叠加显示)"""
    from models.homework import HomeworkImage
    from models.identity_relations import ClassTeacher

    task = task_service.get_task_by_id(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    allowed = task.user_id == user.id
    if not allowed and task.class_id is not None:
        allowed = db.query(ClassTeacher.id).filter(
            ClassTeacher.class_id == task.class_id,
            ClassTeacher.teacher_user_id == user.id,
            ClassTeacher.status == "active",
        ).first() is not None
    if not allowed:
        raise HTTPException(status_code=404, detail="任务不存在")
    image = db.query(HomeworkImage).filter(
        HomeworkImage.task_id == task_id,
        HomeworkImage.image_index == image_index,
    ).order_by(HomeworkImage.image_index, HomeworkImage.id).first()
    if not image or not image.original_url:
        raise HTTPException(status_code=404, detail="图片不存在")
    if image.original_url.startswith(COS_LOCATOR_PREFIX):
        handle, temp_path = tempfile.mkstemp(prefix="homework-preview-")
        os.close(handle)
        try:
            get_cos_provider().download_to(image.original_url, temp_path)
        except Exception:
            try:
                os.remove(temp_path)
            except FileNotFoundError:
                pass
            raise HTTPException(status_code=502, detail="原图暂时无法读取")
        return FileResponse(
            temp_path,
            media_type="image/jpeg",
            background=BackgroundTask(os.remove, temp_path),
        )
    if not os.path.exists(image.original_url):
        raise HTTPException(status_code=404, detail="图片不存在")
    return FileResponse(image.original_url, media_type="image/jpeg")


@router.get("/image/{task_id}/preview-url", response_model=APIResponse)
async def get_original_image_preview_url(
    task_id: str,
    image_index: int = Query(0, ge=0, le=8),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from models.homework import HomeworkImage
    from models.identity_relations import ClassTeacher

    task = task_service.get_task_by_id(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    allowed = task.user_id == user.id
    if not allowed and task.class_id is not None:
        allowed = db.query(ClassTeacher.id).filter(
            ClassTeacher.class_id == task.class_id,
            ClassTeacher.teacher_user_id == user.id,
            ClassTeacher.status == "active",
        ).first() is not None
    if not allowed:
        raise HTTPException(status_code=404, detail="任务不存在")
    image = db.query(HomeworkImage).filter(
        HomeworkImage.task_id == task_id,
        HomeworkImage.image_index == image_index,
    ).order_by(HomeworkImage.image_index, HomeworkImage.id).first()
    if image is None or not image.original_url:
        raise HTTPException(status_code=404, detail="图片不存在")
    if image.original_url.startswith(COS_LOCATOR_PREFIX):
        ttl = max(60, min(int(settings.COS_SIGNED_URL_TTL_SECONDS), 900))
        try:
            url = get_cos_provider().get_signed_download_url(image.original_url)
        except Exception:
            raise HTTPException(status_code=502, detail="原图预览授权暂不可用")
        return APIResponse(data={"storage": "cos", "url": url, "expires_in": ttl})
    return APIResponse(data={"storage": "local", "url": None, "expires_in": None})


# ======================== 状态 / 结果 / 列表 ========================

@router.get("/status/{task_id}", response_model=APIResponse[TaskStatusResponse])
async def get_task_status(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        task = _owned_task(db, task_id, user)
        latest_call = db.query(ModelCallAudit).filter(
            ModelCallAudit.task_id == task_id
        ).order_by(ModelCallAudit.attempt_no.desc()).first()
        failure_code = latest_call.error_code if latest_call else None
        stale_recovery = _is_stale_vision_task(task)
        if stale_recovery and not failure_code:
            failure_code = "WORKER_STATE_STALE_OUTCOME_UNKNOWN"
        if stale_recovery:
            failure_message = "任务超过安全等待时间仍未结束，工作进程可能已中断；远端调用结果未知。系统未自动重试，人工重试可能重复计费。"
        elif failure_code == "VISION_RESPONSE_TIMEOUT_OUTCOME_UNKNOWN":
            failure_message = "批改响应超时，服务端是否已完成不可判定；系统未自动重试。手动重试可能产生重复计费。"
        elif task.status == "FAILED":
            failure_message = "本次批改失败，未生成有效成绩。请检查错误信息后再决定是否手动重试。"
        else:
            failure_message = None
        return APIResponse(data=TaskStatusResponse(
            task_id=task.task_id, status=task.status,
            created_at=task.created_at, updated_at=task.updated_at,
            failure_code=failure_code,
            failure_message=failure_message,
            call_id=latest_call.call_id if latest_call else None,
            can_retry=(task.status == "FAILED" and task.grading_mode == "vision") or stale_recovery,
        ))
    except HTTPException:
        raise
    except Exception as e:
        logger.opt(exception=True).error("查询状态失败: {}", str(e))
        raise HTTPException(status_code=500, detail="查询状态失败")


@router.post("/retry/{task_id}", response_model=APIResponse)
async def retry_failed_homework(
    task_id: str,
    request: HomeworkRetryRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Explicitly requeue one failed task; never perform an automatic replay."""
    task = _owned_task(db, task_id, user)
    stale_recovery = _is_stale_vision_task(task)
    if task.status != "FAILED" and not stale_recovery:
        raise HTTPException(status_code=409, detail="任务仍在处理或尚未超过安全恢复等待时间")
    if task.grading_mode != "vision":
        raise HTTPException(status_code=409, detail="当前只支持视觉批改任务的手动重试")
    if not request.confirm_possible_duplicate_charge:
        raise HTTPException(status_code=422, detail="请确认模型服务端可能已处理上次请求")

    eligible_statuses = [task.status] if stale_recovery else ["FAILED"]
    task_query = db.query(HomeworkTask).filter(
        HomeworkTask.task_id == task_id,
        HomeworkTask.user_id == user.id,
        HomeworkTask.status.in_(eligible_statuses),
    )
    if stale_recovery:
        task_query = task_query.filter(HomeworkTask.updated_at <= _stale_recovery_cutoff())
    changed = task_query.update(
        {
            HomeworkTask.status: "PENDING",
            HomeworkTask.error_message: None,
            HomeworkTask.updated_at: datetime.utcnow(),
        },
        synchronize_session=False,
    )
    if changed != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="任务状态已变化，请刷新后重试")
    if stale_recovery:
        latest_call = db.query(ModelCallAudit).filter(
            ModelCallAudit.task_id == task_id,
            ModelCallAudit.status == "reserved",
        ).order_by(ModelCallAudit.attempt_no.desc()).first()
        if latest_call:
            latest_call.status = "outcome_unknown"
            latest_call.error_code = "WORKER_STATE_STALE_OUTCOME_UNKNOWN"
            latest_call.completed_at = datetime.utcnow()
    db.commit()

    images = task_service.list_task_images(db, task_id)
    if not images:
        db.query(HomeworkTask).filter_by(task_id=task_id, user_id=user.id).update(
            {HomeworkTask.status: "FAILED", HomeworkTask.error_message: "原作业图片不存在，无法安全重试"},
            synchronize_session=False,
        )
        db.commit()
        raise HTTPException(status_code=409, detail="原作业图片不存在，无法重试")
    try:
        process_homework_task.delay(
            task_id, images[0].original_url, task.subject, task.grade, user.id,
            grading_mode="vision", model_name=task.model_name,
        )
    except Exception:
        db.query(HomeworkTask).filter_by(task_id=task_id, user_id=user.id).update(
            {HomeworkTask.status: "FAILED", HomeworkTask.error_message: "重试任务未能进入队列；请检查本地任务服务后再试"},
            synchronize_session=False,
        )
        db.commit()
        raise HTTPException(status_code=503, detail="任务队列暂不可用，未重新调用模型")
    return APIResponse(data={
        "task_id": task_id,
        "status": "PENDING",
        "queued": True,
        "recovered_stale_worker": stale_recovery,
    })


@router.get("/result/{task_id}", response_model=APIResponse[GradingResultResponse])
async def get_grading_result(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        _owned_task(db, task_id, user)
        result = task_service.get_grading_result(db, task_id)
        if not result:
            raise HTTPException(status_code=404, detail="批改结果不存在")
        return APIResponse(data=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.opt(exception=True).error("查询结果失败: {}", str(e))
        raise HTTPException(status_code=500, detail="查询结果失败")


@router.get("/list", response_model=APIResponse)
async def get_homework_list(
    page: int = 1,
    page_size: int = 20,
    subject: Optional[str] = None,
    grade: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        skip = (page - 1) * page_size
        tasks = task_service.get_homework_list(
            db, skip=skip, limit=page_size, subject=subject, grade=grade,
            status=status, user_id=user.id,
        )
        total = task_service.get_homework_count(
            db, subject=subject, grade=grade, status=status, user_id=user.id
        )
        return APIResponse(data={
            "items": tasks, "total": total, "page": page, "page_size": page_size,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.opt(exception=True).error("获取列表失败: {}", str(e))
        raise HTTPException(status_code=500, detail="获取列表失败")


@router.delete("/{task_id}", response_model=APIResponse)
async def delete_homework(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        task = _owned_task(db, task_id, user)
        if task.assignment_id is not None:
            raise HTTPException(status_code=409, detail="班级作业提交不可删除")
        task_service.delete_task(db, task_id)
        return APIResponse(data={"task_id": task_id})
    except HTTPException:
        raise
    except Exception as e:
        logger.opt(exception=True).error("删除失败: {}", str(e))
        raise HTTPException(status_code=500, detail="删除失败")


# ======================== 元数据 ========================

@router.get("/subjects")
async def get_subjects():
    subjects = ["math", "chinese", "english", "physics", "chemistry", "biology", "history", "geography"]
    names = {"math":"数学","chinese":"语文","english":"英语","physics":"物理","chemistry":"化学","biology":"生物","history":"历史","geography":"地理"}
    return APIResponse(data=[{"code": s, "name": names[s]} for s in subjects])


@router.get("/grades")
async def get_grades():
    grades = [f"grade{i}" for i in range(1, 10)]
    names = {f"grade{i}": f"{['','一','二','三','四','五','六','初一','初二','初三'][i]}年级" for i in range(1,10)}
    return APIResponse(data=[{"code": g, "name": names[g]} for g in grades])


@router.get("/statuses")
async def get_statuses():
    statuses = [
        {"code":"PENDING","name":"待处理","description":"任务已创建，等待处理"},
        {"code":"PROCESSING","name":"处理中","description":"正在进行题目识别"},
        {"code":"GRADING","name":"批改中","description":"正在进行智能批改"},
        {"code":"SUCCESS","name":"已完成","description":"批改完成"},
        {"code":"FAILED","name":"失败","description":"处理失败"},
        {"code":"CANCELLED","name":"已取消","description":"任务已取消"},
    ]
    return APIResponse(data=statuses)
