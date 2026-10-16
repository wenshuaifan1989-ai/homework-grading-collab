import json
import os
from contextlib import ExitStack
from celery_app import celery_app
from services.image_service import image_service
from clients.aliyun_client import aliyun_ocr_client
from clients.vision_client import vision_client
from clients.vision_client import VisionResponseTimeout
from services.llm_service import llm_service
from services.task_service import task_service
from config import settings
from utils.logger import logger
from utils.database import SessionLocal
from services.storage_provider import materialize_image
from services.model_quota import finish_vision_call, reserve_vision_call


def _ocr_pipeline(image_path, db, task_id):
    """Mode A: OCR 流水线 — 切题 → 裁剪 → 单题 OCR"""
    # CUTTING
    task_service.update_task_status(db, task_id, "CUTTING")
    question_blocks = aliyun_ocr_client.recognize_edu_paper_cut(image_path)
    n = len(question_blocks)
    logger.info(f"切题完成，共 {n} 道题")

    cropped = image_service.crop_question_blocks(image_path, question_blocks)
    task_service.save_question_blocks(db, task_id, cropped)

    # OCRING
    task_service.update_task_status(db, task_id, "OCRING")
    ocr_results = []
    for idx, block in enumerate(cropped):
        enhanced_path = image_service.enhance_for_ocr(block["image_path"])
        ocr = aliyun_ocr_client.recognize_edu_question_ocr(enhanced_path)

        if not ocr.get("question_text"):
            ocr = aliyun_ocr_client.recognize_edu_question_ocr(block["image_path"])

        if not ocr.get("question_text") and idx < len(question_blocks):
            t = question_blocks[idx].get("text", "")
            if t:
                ocr["question_text"] = t

        ocr["question_block_id"] = block["id"]
        ocr["question_no"] = block["question_no"]
        ocr_results.append(ocr)

    task_service.save_ocr_results(db, task_id, ocr_results)
    return ocr_results


MAX_IMAGES_PER_TASK = 9


def _persist_vision_image(db, task_id, image_index, image_path, grading_dicts):
    """G2: 持久化单张图片的题目/OCR/批改结果，返回 (本页得分, 本页题数)。"""
    from models.homework import QuestionBlock  # noqa: F401  (保持与既有导入一致)
    from schemas.homework import GradingResult

    virtual_blocks = [
        {"question_no": r["question_no"], "image_path": image_path,
         "x1": 0, "y1": 0, "x2": 100, "y2": 80, "image_index": image_index}
        for r in grading_dicts
    ]
    created = task_service.save_question_blocks(db, task_id, virtual_blocks)

    ocr_results = []
    grading_results = []
    subtotal = 0.0

    for r, b in zip(grading_dicts, created):
        ocr_results.append({
            "question_block_id": b.id, "question_no": r["question_no"],
            "question_text": r["question_text"], "student_answer": r["student_answer"],
            "question_type": r["question_type"], "raw_response": r.get("raw_response", {}),
        })

        gr = GradingResult(
            question_block_id=b.id, question_no=r["question_no"],
            score=r["score"], max_score=r["max_score"],
            accuracy=r.get("accuracy", round(r["score"]/max(r["max_score"],1)*100, 1)),
            result=r["result"], comment=r.get("comment", ""),
            analysis=r.get("analysis", ""),
            confidence=r.get("confidence"), raw_response=r.get("raw_response", {}),
            correct_answer=r.get("correct_answer"),
            error_type=r.get("error_type"),
            knowledge_points=r.get("knowledge_points") or [],
            difficulty=r.get("difficulty") or "unknown",
        )
        subtotal += float(gr.score)
        grading_results.append(gr)
        logger.info(
            f"[image {image_index}] 批改 #{r['question_no']}: "
            f"score={r['score']}/{r['max_score']} result={r['result']} "
            f"difficulty={gr.difficulty} error_type={gr.error_type}"
        )

    task_service.save_ocr_results(db, task_id, ocr_results)
    task_service.save_grading_results(db, task_id, grading_results)
    return subtotal, len(grading_results)


def _resolve_vision_config(model_name=None):
    cfg = None
    if model_name:
        cfg = settings.get_model_by_name(model_name)
        if cfg and cfg.type != "vision":
            logger.warning(f"模型 {model_name} 不是视觉模型，自动切换")
            cfg = None

    if not cfg:
        if settings.vision_models:
            cfg = settings.vision_models[0]
        elif settings.text_models:
            cfg = settings.text_models[0]
            logger.info(f"无视觉模型，尝试用文本模型 {cfg.name}")
        else:
            raise Exception("未配置任何可用模型")
    return cfg


def _vision_pipeline(image_path, db, task_id, model_name=None):
    """Mode B: 视觉大模型一步到位。

    G2: 支持 1..9 张图片，按上传顺序在**同一个 HomeworkTask** 内批改；
    多图共用一次视觉模型请求，再按模型返回的 image_index 归属各页；
    任一页缺少结果则整体 FAILED 并记录 failed_image_index；
    每次尝试先清理本任务派生数据，保证重试/重放幂等。
    """
    task_service.update_task_status(db, task_id, "GRADING")

    cfg = _resolve_vision_config(model_name)
    logger.info(f"视觉批改使用模型: {cfg.name} ({cfg.model_id})")
    from models.learning import AssignmentVariantQuestion, AssignmentVariantTask

    variant_link = db.query(AssignmentVariantTask).filter_by(task_id=task_id).first()
    assignment_questions = None
    prompt_version = vision_client.PROMPT_VERSION
    if variant_link is not None:
        assignment_questions = [
            {
                "question_text": row.question_text,
                "options": row.options_json,
                "correct_answer": row.correct_answer,
                "analysis": row.analysis,
                "max_score": float(row.max_score),
            }
            for row in db.query(AssignmentVariantQuestion)
            .filter_by(variant_id=variant_link.variant_id)
            .order_by(AssignmentVariantQuestion.sort_order, AssignmentVariantQuestion.id)
            .all()
        ]
        if not assignment_questions:
            message = "分层作业版本没有题目，不能执行批改"
            task_service.mark_task_failed(db, task_id, message)
            raise ValueError(message)
        prompt_version = vision_client.ASSIGNMENT_VARIANT_PROMPT_VERSION
    task_service.set_task_traceability(db, task_id, cfg.name, prompt_version)

    # 图片集合：优先 DB 中已保存的顺序（重试时同样成立），回退到单图入参
    images = task_service.list_task_images(db, task_id)
    paths = [im.original_url for im in images] or ([image_path] if image_path else [])
    if not paths:
        raise Exception("任务没有可用图片")
    if len(paths) > MAX_IMAGES_PER_TASK:
        raise Exception(f"单个任务最多 {MAX_IMAGES_PER_TASK} 张图片")

    # 幂等：清空既有派生数据后再重建，避免重试产生重复 QuestionBlock/OCR/Grading
    task_service.reset_task_derived_data(db, task_id)

    total_score = 0.0
    total_questions = 0
    failed_index = None
    try:
        with ExitStack() as stack:
            local_paths = [
                stack.enter_context(materialize_image(locator)) for locator in paths
            ]
            call_id = reserve_vision_call(db, task_id, cfg.provider, cfg.name)
            try:
                if assignment_questions:
                    grading_dicts = vision_client.grade_homework_images_directly(
                        local_paths, cfg, assignment_questions=assignment_questions
                    )
                else:
                    grading_dicts = vision_client.grade_homework_images_directly(local_paths, cfg)
            except VisionResponseTimeout:
                finish_vision_call(db, call_id, "outcome_unknown", VisionResponseTimeout.code)
                logger.error("Vision call outcome unknown: task_id={}, call_id={}", task_id, call_id)
                raise
            except Exception:
                finish_vision_call(db, call_id, "provider_error", "VISION_PROVIDER_ERROR")
                logger.error("Vision provider request failed: task_id={}, call_id={}", task_id, call_id)
                raise
            else:
                finish_vision_call(db, call_id, "response_received")
        if assignment_questions:
            _apply_variant_grading_contract(grading_dicts, assignment_questions)
        if not grading_dicts:
            raise Exception("视觉模型未识别到任何题目")

        results_by_image = {index: [] for index in range(len(paths))}
        for result in grading_dicts:
            image_index = result.get("image_index")
            # Legacy single-image results have no image index.
            if image_index is None and len(paths) == 1:
                image_index = 0
            if image_index not in results_by_image:
                raise Exception("视觉模型返回了无效的图片页序")
            results_by_image[image_index].append(result)

        for index, locator in enumerate(paths):
            failed_index = index
            page_results = results_by_image[index]
            if not page_results:
                raise Exception(f"视觉模型未识别到第 {index + 1} 页题目")
            subtotal, count = _persist_vision_image(
                db, task_id, index, locator, page_results
            )
            total_score += subtotal
            total_questions += count
            logger.info(
                f"图片 {index + 1}/{len(paths)} 完成: {count} 题, 小计={subtotal}"
            )
            failed_index = None
    except Exception as e:
        failure_message = (
            f"分层作业批改未通过题目对齐校验：{e}"
            if assignment_questions
            else f"第 {(failed_index if failed_index is not None else 0) + 1} 张图片处理失败: {e}"
        )
        task_service.mark_task_failed(
            db,
            task_id,
            failure_message,
            failed_index,
        )
        raise

    task_service.update_task_total_score(db, task_id, total_score)
    task_service.clear_task_failure(db, task_id)
    logger.info(
        f"多图视觉批改完成: images={len(paths)}, total_questions={total_questions}, "
        f"total_score={total_score}"
    )
    return total_score, total_questions


def _normalized_question_no(value):
    import re
    match = re.search(r"\d+", str(value or ""))
    return str(int(match.group(0))) if match else None


def _apply_variant_grading_contract(grading_dicts, assignment_questions):
    """Fail closed if the model does not grade exactly the assigned question set."""
    if len(grading_dicts) != len(assignment_questions):
        raise ValueError("视觉批改题数与教师布置的分层作业题数不一致")
    by_number = {}
    for result in grading_dicts:
        number = _normalized_question_no(result.get("question_no"))
        if number is None or number in by_number:
            raise ValueError("视觉批改题号缺失或重复，不能与分层作业题目可靠匹配")
        by_number[number] = result

    reconciled = []
    for index, expected in enumerate(assignment_questions, start=1):
        result = by_number.get(str(index))
        if result is None:
            raise ValueError("视觉批改结果缺少教师布置的第 {} 题".format(index))
        max_score = float(expected["max_score"])
        score = float(result.get("score", -1))
        if score < 0 or score > max_score:
            raise ValueError("视觉批改得分超出教师设定的满分范围")
        result["question_no"] = str(index)
        result["question_text"] = expected["question_text"]
        result["max_score"] = max_score
        result["accuracy"] = round(score / max_score * 100, 1) if max_score > 0 else 0
        result["correct_answer"] = expected.get("correct_answer") or result.get("correct_answer")
        result["analysis"] = expected.get("analysis") or result.get("analysis")
        reconciled.append(result)
    return reconciled


def _ocr_pipeline_from_blocks(image_path, db, task_id, selected_indices=""):
    """使用已保存的切题区域进行 OCR（跳过 paper cut 步骤）"""
    from models.homework import QuestionBlock

    task_service.update_task_status(db, task_id, "OCRING")

    all_blocks = (
        db.query(QuestionBlock)
        .filter(QuestionBlock.task_id == task_id)
        .order_by(QuestionBlock.id)
        .all()
    )

    # 筛选选中的区域
    if selected_indices:
        try:
            indices = json.loads(selected_indices)
            blocks = [all_blocks[i] for i in indices if i < len(all_blocks)]
            logger.info(f"使用选中区域: {indices}, 共 {len(blocks)} 块")
        except Exception:
            blocks = all_blocks
    else:
        blocks = all_blocks

    from services.image_service import image_service

    ocr_results = []
    for b in blocks:
        if b.question_image_url and os.path.exists(b.question_image_url):
            img_path = b.question_image_url
        else:
            img_path = image_path

        enhanced_path = image_service.enhance_for_ocr(img_path)
        ocr = aliyun_ocr_client.recognize_edu_question_ocr(enhanced_path)

        if not ocr.get("question_text"):
            ocr = aliyun_ocr_client.recognize_edu_question_ocr(img_path)

        ocr["question_block_id"] = b.id
        ocr["question_no"] = b.question_no
        ocr_results.append(ocr)

    task_service.save_ocr_results(db, task_id, ocr_results)
    return ocr_results


def _grading_loop(ocr_results, db, task_id, model_name, subject="", grade=""):
    """逐题批改：优先查标准答案，有标答用标答参考批改，无标答让 LLM 直接解题"""
    task_service.update_task_status(db, task_id, "GRADING")
    total_score = 0.0
    grading_results = []

    for ocr in ocr_results:
        q_text = ocr.get("question_text", "")
        s_answer = ocr.get("student_answer", "")
        q_type = ocr.get("question_type", "解答题")

        if not q_text:
            from schemas.homework import GradingResult
            gr = GradingResult(
                question_block_id=ocr.get("question_block_id", 0),
                question_no=ocr.get("question_no", ""),
                score=0, max_score=0, accuracy=0,
                result="待复核", comment="题目识别失败",
            )
        else:
            std = task_service.match_standard_answer(db, subject, grade, q_text)
            if std is not None:
                logger.info(f"#{ocr.get('question_no','?')} 匹配到标准答案: {std.question_key}")
                gr = llm_service.grade_with_answer(
                    question_type=std.question_type,
                    question_text=q_text,
                    student_answer=s_answer,
                    standard_answer=std.standard_answer,
                    max_score=float(std.max_score),
                    model_name=model_name,
                )
            else:
                gr = llm_service.grade_without_answer(
                    question_type=q_type,
                    question_text=q_text,
                    student_answer=s_answer,
                    max_score=10.0,
                    model_name=model_name,
                )

        gr.question_block_id = ocr.get("question_block_id", 0)
        gr.question_no = ocr.get("question_no", "")
        total_score += gr.score
        grading_results.append(gr)
        logger.info(
            f"批改 #{gr.question_no}: score={gr.score}/{gr.max_score} "
            f"accuracy={gr.accuracy}% result={gr.result} "
            f"comment={gr.comment[:30] if gr.comment else ''}"
        )

    total_accuracy = None
    if grading_results:
        accs = [r.accuracy for r in grading_results if r.accuracy is not None]
        if accs:
            total_accuracy = round(sum(accs) / len(accs), 1)

    task_service.save_grading_results(db, task_id, grading_results)
    task_service.update_task_total_score(db, task_id, total_score)
    logger.info(f"全卷批改完成: total_score={total_score}, total_accuracy={total_accuracy}%")
    return total_score, grading_results


@celery_app.task(
    bind=True, max_retries=0, soft_time_limit=150, time_limit=180,
    name="tasks.homework_tasks.process_homework_task"
)
def process_homework_task(
    self, task_id: str, image_path: str, subject: str, grade: str,
    user_id: int, grading_mode: str = "ocr", model_name: str = None,
):
    """处理作业批改任务"""
    db = SessionLocal()
    try:
        if not task_service.claim_task_for_processing(db, task_id):
            task = task_service.get_task_by_id(db, task_id)
            status = task.status if task else "MISSING"
            logger.warning("跳过重复/非待处理批改消息: task_id={}, status={}", task_id, status)
            return {"task_id": task_id, "status": status, "skipped_duplicate": True}
        persisted_task = task_service.get_task_by_id(db, task_id)
        if persisted_task and persisted_task.grading_mode == "known":
            grading_mode = "known"
        task_service.update_task_grading_mode(db, task_id, grading_mode)
        logger.info(f"开始处理: {task_id}, mode={grading_mode}, model={model_name}")

        if grading_mode == "known":
            from services.known_assignment_grading import process_known
            return process_known(db, task_id)

        # 分析与批改
        if grading_mode == "vision":
            # Mode B: 视觉模型一步到位，直接批改
            total_score, _ = _vision_pipeline(image_path, db, task_id, model_name)
        else:
            # Mode A: OCR 流水线 → 逐题 LLM 批改
            with materialize_image(image_path) as local_path:
                ocr_results = _ocr_pipeline(local_path, db, task_id)
            total_score, _ = _grading_loop(ocr_results, db, task_id, model_name, subject, grade)

        task_service.update_task_status(db, task_id, "SUCCESS")
        logger.info(f"批改完成: {task_id}, 总分: {total_score}")
        return {"task_id": task_id, "status": "SUCCESS", "total_score": total_score}

    except Exception as e:
        logger.opt(exception=True).error(
            "任务失败: task_id={}, 错误: {}", task_id, str(e)
        )
        db.rollback()
        task_service.update_task_status(db, task_id, "FAILED", str(e))
        # Never automatically replay an external vision request: a response
        # timeout can leave remote completion/billing uncertain. Recovery is an
        # explicit, quota-gated user action through the retry API.
        raise
    finally:
        db.close()


@celery_app.task(
    bind=True, max_retries=0, soft_time_limit=150, time_limit=180,
    name="tasks.homework_tasks.process_analyze_task"
)
def process_analyze_task(
    self, task_id: str, image_path: str, subject: str, grade: str,
    user_id: int, grading_mode: str = "ocr", model_name: str = None,
    selected_indices: str = "",
):
    """分析并批改作业"""
    if grading_mode == "known":
        raise ValueError("Known assignments must use process_homework_task; no external fallback")
    db = SessionLocal()
    try:
        task_service.update_task_status(db, task_id, "PROCESSING")
        task_service.update_task_grading_mode(db, task_id, grading_mode)
        logger.info(f"开始分析: {task_id}, mode={grading_mode}, model={model_name}")

        if grading_mode == "vision":
            total_score, _ = _vision_pipeline(image_path, db, task_id, model_name)
        else:
            ocr_results = _ocr_pipeline_from_blocks(image_path, db, task_id, selected_indices)
            total_score, _ = _grading_loop(ocr_results, db, task_id, model_name, subject, grade)

        task_service.update_task_status(db, task_id, "SUCCESS")
        logger.info(f"分析批改完成: {task_id}, 总分: {total_score}")
        return {"task_id": task_id, "status": "SUCCESS", "total_score": total_score}

    except Exception as e:
        logger.opt(exception=True).error("分析失败: task_id={}, 错误: {}", task_id, str(e))
        db.rollback()
        task_service.update_task_status(db, task_id, "FAILED", str(e))
        raise
    finally:
        db.close()


@celery_app.task(
    bind=True, max_retries=3, name="tasks.homework_tasks.process_grade_only_task"
)
def process_grade_only_task(self, task_id: str, model_name: str):
    """对已有分析结果用新模型重新批改"""
    db = SessionLocal()
    try:
        from models.homework import OCRResult
        ocr_rows = (
            db.query(OCRResult).filter(OCRResult.task_id == task_id).all()
        )
        if not ocr_rows:
            raise Exception("未找到OCR分析结果")

        ocr_results = [
            {
                "question_block_id": r.question_block_id,
                "question_no": r.question_no,
                "question_text": r.question_text or "",
                "student_answer": r.student_answer or "",
                "question_type": r.question_type or "解答题",
            }
            for r in ocr_rows
        ]

        task = task_service.get_task_by_id(db, task_id)
        total_score, _ = _grading_loop(
            ocr_results, db, task_id, model_name,
            subject=task.subject if task else "",
            grade=task.grade if task else "",
        )
        task_service.update_task_status(db, task_id, "SUCCESS")
        logger.info(f"重新批改完成: {task_id}, model={model_name}, 总分={total_score}")
        return {"task_id": task_id, "status": "SUCCESS", "total_score": total_score}

    except Exception as e:
        logger.opt(exception=True).error("重新批改失败: {}", str(e))
        db.rollback()
        raise
    finally:
        db.close()
