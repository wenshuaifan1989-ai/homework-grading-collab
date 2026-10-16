import re
from sqlalchemy.orm import Session
from sqlalchemy import update
from models.homework import (
    HomeworkTask,
    HomeworkImage,
    QuestionBlock,
    OCRResult,
    GradingResult as GradingResultModel,
    StandardAnswer,
)
from models.learning import AssignmentVariantTask
from schemas.homework import GradingResult
from utils.logger import logger
from typing import Optional, List
from decimal import Decimal


class TaskService:
    def claim_task_for_processing(self, db: Session, task_id: str) -> bool:
        """Claim a pending task exactly once before starting paid processing."""
        changed = db.execute(
            update(HomeworkTask)
            .where(HomeworkTask.task_id == task_id, HomeworkTask.status == "PENDING")
            .values(status="PROCESSING", error_message=None)
        )
        db.commit()
        return changed.rowcount == 1

    def create_task(
        self,
        db: Session,
        task_id: str,
        user_id: int,
        subject: str,
        grade: str,
        file_path: str,
        grading_mode: Optional[str] = None,
    ) -> HomeworkTask:
        """G2: 兼容旧单图调用，内部统一走多图建任务。"""
        return self.create_task_with_images(
            db, task_id, user_id, subject, grade, [file_path], grading_mode=grading_mode
        )

    def create_task_with_images(
        self,
        db: Session,
        task_id: str,
        user_id: int,
        subject: str,
        grade: str,
        image_paths: List[str],
        grading_mode: Optional[str] = None,
        assignment_id: Optional[int] = None,
        class_id: Optional[int] = None,
        student_id: Optional[int] = None,
        actor_user_id: Optional[int] = None,
        assignment_variant_id: Optional[int] = None,
    ) -> HomeworkTask:
        """G2: 建 1 个 HomeworkTask + N 个带顺序的 HomeworkImage（1 份作业=1 任务）。"""
        task = HomeworkTask(
            task_id=task_id,
            user_id=user_id,
            subject=subject,
            grade=grade,
            status="PENDING",
            grading_mode=grading_mode,
            assignment_id=assignment_id,
            class_id=class_id,
            student_id=student_id,
            actor_user_id=actor_user_id or user_id,
        )
        db.add(task)
        db.flush()
        db.add_all([
            HomeworkImage(task_id=task_id, original_url=path, image_index=index)
            for index, path in enumerate(image_paths)
        ])
        if assignment_variant_id is not None:
            if assignment_id is None or class_id is None or student_id is None:
                db.rollback()
                raise ValueError("分层作业提交必须绑定作业、班级和真实学生")
            db.add(AssignmentVariantTask(
                task_id=task_id,
                assignment_id=assignment_id,
                student_id=student_id,
                variant_id=assignment_variant_id,
            ))
        db.commit()
        db.refresh(task)

        logger.info(f"创建作业任务: {task_id}, image_count={len(image_paths)}")
        return task

    def list_task_images(self, db: Session, task_id: str) -> List[HomeworkImage]:
        """G2: 按上传顺序返回任务图片。"""
        return (
            db.query(HomeworkImage)
            .filter(HomeworkImage.task_id == task_id)
            .order_by(HomeworkImage.image_index, HomeworkImage.id)
            .all()
        )

    def reset_task_derived_data(self, db: Session, task_id: str) -> dict:
        """G2 幂等：清除本任务已有题目/OCR/批改派生数据，供重试或重放时重建，避免重复脏数据。"""
        deleted = {
            "grading_results": db.query(GradingResultModel)
            .filter(GradingResultModel.task_id == task_id)
            .delete(synchronize_session=False),
            "ocr_results": db.query(OCRResult)
            .filter(OCRResult.task_id == task_id)
            .delete(synchronize_session=False),
            "question_blocks": db.query(QuestionBlock)
            .filter(QuestionBlock.task_id == task_id)
            .delete(synchronize_session=False),
        }
        db.commit()
        logger.info(f"清理任务派生数据(幂等): {task_id}, {deleted}")
        return deleted

    def set_task_traceability(
        self, db: Session, task_id: str, model_name: Optional[str], prompt_version: Optional[str]
    ):
        """G2: 记录本次批改所用模型/prompt 版本（不记录任何密钥）。"""
        task = self.get_task_by_id(db, task_id)
        if task:
            if model_name:
                task.model_name = model_name
            if prompt_version:
                task.prompt_version = prompt_version
            db.commit()

    def mark_task_failed(
        self,
        db: Session,
        task_id: str,
        error_message: str,
        failed_image_index: Optional[int] = None,
    ):
        """G2: 任务失败并定位失败图片序号（不伪装 SUCCESS）。"""
        task = self.get_task_by_id(db, task_id)
        if task:
            task.status = "FAILED"
            task.error_message = error_message
            if failed_image_index is not None:
                task.failed_image_index = failed_image_index
            db.commit()
            logger.error(
                f"任务失败: {task_id}, failed_image_index={failed_image_index}, {error_message}"
            )

    def get_task_by_id(self, db: Session, task_id: str) -> Optional[HomeworkTask]:
        return db.query(HomeworkTask).filter(HomeworkTask.task_id == task_id).first()

    def update_task_status(
        self, db: Session, task_id: str, status: str, error_message: str = None
    ):
        task = self.get_task_by_id(db, task_id)
        if task:
            task.status = status
            if error_message:
                task.error_message = error_message
            db.commit()
            logger.info(f"更新任务状态: {task_id} -> {status}")

    def update_task_total_score(self, db: Session, task_id: str, total_score: float):
        task = self.get_task_by_id(db, task_id)
        if task:
            task.total_score = Decimal(str(total_score))
            db.commit()

    def save_processed_image(self, db: Session, task_id: str, processed_path: str):
        image = db.query(HomeworkImage).filter(HomeworkImage.task_id == task_id).first()
        if image:
            image.processed_url = processed_path
            db.commit()
        else:
            logger.warning(f"未找到任务 {task_id} 的图片记录")

    def save_question_blocks(self, db: Session, task_id: str, blocks: List[dict]):
        created = []
        for block in blocks:
            question_block = QuestionBlock(
                task_id=task_id,
                question_no=block["question_no"],
                question_image_url=block["image_path"],
                x1=block["x1"],
                y1=block["y1"],
                x2=block["x2"],
                y2=block["y2"],
                image_index=block.get("image_index", 0),
            )
            db.add(question_block)
            created.append(question_block)
        db.commit()

        # G2: 直接回填本次新建对象的主键，避免多图多次调用时错配 id
        for block, question_block in zip(blocks, created):
            block["id"] = question_block.id
        return created

    def save_question_blocks_raw(
        self, db: Session, task_id: str, question_blocks: list, image_path: str,
        image_index: int = 0,
    ):
        """保存切题原始坐标（不裁剪图片，用于前端预览）"""
        from services.image_service import image_service

        cropped = image_service.crop_question_blocks(image_path, question_blocks)
        for i, block in enumerate(cropped):
            qb = QuestionBlock(
                task_id=task_id,
                question_no=block.get("question_no", str(i + 1)),
                question_image_url=block["image_path"],
                x1=block["x1"], y1=block["y1"],
                x2=block["x2"], y2=block["y2"],
                image_index=image_index,
            )
            db.add(qb)
        db.commit()

    def save_ocr_results(self, db: Session, task_id: str, ocr_results: List[dict]):
        for ocr_result in ocr_results:
            ocr = OCRResult(
                task_id=task_id,
                question_block_id=ocr_result["question_block_id"],
                question_no=ocr_result["question_no"],
                question_text=ocr_result.get("question_text", ""),
                student_answer=ocr_result.get("student_answer", ""),
                question_type=ocr_result.get("question_type", ""),
                raw_response=ocr_result.get("raw_response", {}),
            )
            db.add(ocr)
        db.commit()

    def save_grading_results(
        self, db: Session, task_id: str, grading_results: List[GradingResult]
    ):
        for result in grading_results:
            grading = GradingResultModel(
                task_id=task_id,
                question_block_id=result.question_block_id,
                question_no=result.question_no,
                score=Decimal(str(result.score)),
                max_score=Decimal(str(result.max_score)),
                accuracy=(
                    Decimal(str(result.accuracy)) if result.accuracy is not None else None
                ),
                result=result.result,
                comment=result.comment or "",
                analysis=result.analysis or "",
                confidence=(
                    Decimal(str(result.confidence)) if result.confidence is not None else None
                ),
                correct_answer=getattr(result, "correct_answer", None),
                error_type=getattr(result, "error_type", None),
                knowledge_points=getattr(result, "knowledge_points", None),
                difficulty=getattr(result, "difficulty", None),
                raw_response=result.raw_response,
            )
            db.add(grading)
        db.commit()

    def update_task_grading_mode(self, db: Session, task_id: str, grading_mode: str):
        task = self.get_task_by_id(db, task_id)
        if task:
            task.grading_mode = grading_mode
            db.commit()

    def clear_task_failure(self, db: Session, task_id: str):
        """G2: 任务成功后清除历史失败痕迹，避免重试成功后残留 failed_image_index。"""
        task = self.get_task_by_id(db, task_id)
        if task:
            task.error_message = None
            task.failed_image_index = None
            db.commit()

    def get_grading_result(self, db: Session, task_id: str) -> Optional[dict]:
        task = self.get_task_by_id(db, task_id)
        if not task:
            return None

        images = self.list_task_images(db, task_id)
        block_rows = (
            db.query(QuestionBlock)
            .filter(QuestionBlock.task_id == task_id)
            .order_by(QuestionBlock.image_index, QuestionBlock.id)
            .all()
        )
        block_by_id = {b.id: b for b in block_rows}

        grading_results = (
            db.query(GradingResultModel)
            .filter(GradingResultModel.task_id == task_id)
            .all()
        )
        # G2: 按（图片顺序 → 题块顺序）稳定排序，跨页重复题号不合并、不覆盖
        grading_results = sorted(
            grading_results,
            key=lambda r: (
                block_by_id[r.question_block_id].image_index
                if r.question_block_id in block_by_id else 0,
                r.question_block_id,
            ),
        )
        ocr_by_block = {
            row.question_block_id: row
            for row in db.query(OCRResult)
            .filter(OCRResult.task_id == task_id)
            .all()
        }

        def _image_index(block_id: int):
            block = block_by_id.get(block_id)
            return block.image_index if block else None

        results = [
            GradingResult(
                question_block_id=r.question_block_id,
                question_no=r.question_no,
                question_text=(ocr_by_block.get(r.question_block_id).question_text
                               if ocr_by_block.get(r.question_block_id) else None),
                student_answer=(ocr_by_block.get(r.question_block_id).student_answer
                                if ocr_by_block.get(r.question_block_id) else None),
                question_type=(ocr_by_block.get(r.question_block_id).question_type
                               if ocr_by_block.get(r.question_block_id) else None),
                score=float(r.score),
                max_score=float(r.max_score),
                accuracy=float(r.accuracy) if r.accuracy is not None else None,
                result=r.result,
                comment=r.comment,
                analysis=r.analysis,
                confidence=float(r.confidence) if r.confidence else None,
                image_index=_image_index(r.question_block_id),
                correct_answer=r.correct_answer,
                error_type=r.error_type,
                knowledge_points=list(r.knowledge_points) if r.knowledge_points else [],
                difficulty=r.difficulty,
            )
            for r in grading_results
        ]

        total_acc = None
        if results:
            accs = [r.accuracy for r in results if r.accuracy is not None]
            if accs:
                total_acc = round(sum(accs) / len(accs), 1)

        correct_count = sum(1 for r in results if r.result == "correct")
        partial_count = sum(1 for r in results if r.result == "partial")
        wrong_count = sum(1 for r in results if r.result == "wrong")
        total_max_score = round(sum(r.max_score for r in results), 2)

        # G2: 按图片顺序的摘要（不暴露本地文件路径）
        images_summary = []
        for image in images:
            images_summary.append({
                "image_index": image.image_index,
                "question_count": sum(
                    1 for b in block_rows if b.image_index == image.image_index
                ),
            })

        return {
            "task_id": task_id,
            "status": task.status,
            "image_count": len(images),
            "total_score": float(task.total_score) if task.total_score else 0,
            "total_max_score": total_max_score,
            "total_accuracy": total_acc,
            "grading_mode": task.grading_mode,
            "model_name": task.model_name,
            "prompt_version": task.prompt_version,
            "failed_image_index": task.failed_image_index,
            "total_questions": len(results),
            "correct_count": correct_count,
            "partial_count": partial_count,
            "wrong_count": wrong_count,
            "images": images_summary,
            "results": results,
            "created_at": task.created_at,
        }

    def get_homework_list(
        self, db, skip: int = 0, limit: int = 20,
        subject: Optional[str] = None, grade: Optional[str] = None,
        status: Optional[str] = None, user_id: Optional[int] = None,
    ):
        query = db.query(HomeworkTask).order_by(HomeworkTask.created_at.desc())

        if user_id is not None:
            query = query.filter(HomeworkTask.user_id == user_id)
        
        if subject:
            query = query.filter(HomeworkTask.subject == subject)
        if grade:
            query = query.filter(HomeworkTask.grade == grade)
        if status:
            query = query.filter(HomeworkTask.status == status)
        
        tasks = query.offset(skip).limit(limit).all()

        result = []
        for task in tasks:
            grading_results = (
                db.query(GradingResultModel)
                .filter(GradingResultModel.task_id == task.task_id)
                .all()
            )
            
            accuracy_sum = 0
            accuracy_count = 0
            
            questions = []
            for gr in grading_results:
                if gr.accuracy is not None:
                    accuracy_sum += float(gr.accuracy)
                    accuracy_count += 1
                
                questions.append({
                    "question_no": gr.question_no,
                    "question_text": gr.analysis[:50] + "..." if gr.analysis and len(gr.analysis) > 50 else (gr.analysis or ""),
                    "accuracy": float(gr.accuracy) if gr.accuracy else 0,
                    "result": gr.result,
                })
            
            accuracy = round(accuracy_sum / accuracy_count, 1) if accuracy_count > 0 else 0

            result.append(
                {
                    "task_id": task.task_id,
                    "assignment_id": task.assignment_id,
                    "subject": task.subject,
                    "status": task.status,
                    "accuracy": accuracy,
                    "created_at": task.created_at,
                    "questions": questions,
                    "question_count": len(questions),
                }
            )

        return result

    def get_homework_count(
        self, db, subject: Optional[str] = None, grade: Optional[str] = None,
        status: Optional[str] = None, user_id: Optional[int] = None,
    ) -> int:
        query = db.query(HomeworkTask)

        if user_id is not None:
            query = query.filter(HomeworkTask.user_id == user_id)
        
        if subject:
            query = query.filter(HomeworkTask.subject == subject)
        if grade:
            query = query.filter(HomeworkTask.grade == grade)
        if status:
            query = query.filter(HomeworkTask.status == status)
        
        return query.count()

    def delete_task(self, db: Session, task_id: str):
        """删除任务及其相关数据"""
        db.query(GradingResultModel).filter(GradingResultModel.task_id == task_id).delete()
        db.query(OCRResult).filter(OCRResult.task_id == task_id).delete()
        db.query(QuestionBlock).filter(QuestionBlock.task_id == task_id).delete()
        db.query(HomeworkImage).filter(HomeworkImage.task_id == task_id).delete()
        db.query(HomeworkTask).filter(HomeworkTask.task_id == task_id).delete()
        db.commit()
        logger.info(f"删除任务: {task_id}")


    def match_standard_answer(
        self, db: Session, subject: str, grade: str, question_text: str
    ) -> Optional[StandardAnswer]:
        """匹配标准答案：清理文本后 LIKE + n-gram 中文匹配"""
        if not question_text:
            return None
        try:
            # 1. 精确匹配
            exact = (
                db.query(StandardAnswer)
                .filter(
                    StandardAnswer.subject == subject,
                    StandardAnswer.grade == grade,
                    StandardAnswer.question_text == question_text.strip(),
                )
                .first()
            )
            if exact:
                return exact

            # 2. 清理标点数字，取核心中文
            clean = re.sub(
                r"[\d\s.,，。、！？：；（）()\[\]【】~`@#$%^&*+\-=/\\|《》〈〉\"'""''?!:;△○　]",
                "",
                question_text,
            )
            if len(clean) >= 3:
                fuzzy = (
                    db.query(StandardAnswer)
                    .filter(
                        StandardAnswer.subject == subject,
                        StandardAnswer.grade == grade,
                        StandardAnswer.question_text.like(f"%{clean[:20]}%"),
                    )
                    .first()
                )
                if fuzzy:
                    return fuzzy

            # 3. n-gram 滑动窗口
            if len(clean) >= 5:
                for i in range(0, len(clean) - 4, 3):
                    gram = clean[i : i + 5]
                    m = (
                        db.query(StandardAnswer)
                        .filter(
                            StandardAnswer.subject == subject,
                            StandardAnswer.grade == grade,
                            StandardAnswer.question_text.like(f"%{gram}%"),
                        )
                        .first()
                    )
                    if m:
                        return m

            return None
        except Exception as e:
            logger.error(f"匹配标准答案失败: {e}")
            return None


task_service = TaskService()
