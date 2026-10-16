"""标准答案管理 API — CRUD 操作，数据存储在 MySQL"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from utils.database import get_db
from models.homework import StandardAnswer
from schemas.common import APIResponse
from utils.logger import logger

router = APIRouter(prefix="/answers", tags=["标准答案管理"])


class StandardAnswerCreate(BaseModel):
    subject: str
    grade: str
    question_key: str
    question_text: str
    standard_answer: str
    question_type: str = "解答题"
    max_score: float = 10.0


class StandardAnswerUpdate(BaseModel):
    subject: Optional[str] = None
    grade: Optional[str] = None
    question_text: Optional[str] = None
    standard_answer: Optional[str] = None
    question_type: Optional[str] = None
    max_score: Optional[float] = None


class StandardAnswerOut(BaseModel):
    id: int
    subject: str
    grade: str
    question_key: str
    question_text: str
    standard_answer: str
    question_type: str
    max_score: float


@router.get("", response_model=APIResponse[List[StandardAnswerOut]])
def list_answers(
    subject: Optional[str] = Query(None),
    grade: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """查询标准答案列表，可按 subject/grade 筛选"""
    q = db.query(StandardAnswer)
    if subject:
        q = q.filter(StandardAnswer.subject == subject)
    if grade:
        q = q.filter(StandardAnswer.grade == grade)
    rows = q.order_by(StandardAnswer.id).all()
    return APIResponse(data=[StandardAnswerOut(
        id=r.id, subject=r.subject, grade=r.grade,
        question_key=r.question_key, question_text=r.question_text,
        standard_answer=r.standard_answer, question_type=r.question_type,
        max_score=float(r.max_score),
    ) for r in rows])


@router.get("/{answer_id}", response_model=APIResponse[StandardAnswerOut])
def get_answer(answer_id: int, db: Session = Depends(get_db)):
    """获取单条标准答案"""
    r = db.query(StandardAnswer).filter(StandardAnswer.id == answer_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="标准答案不存在")
    return APIResponse(data=StandardAnswerOut(
        id=r.id, subject=r.subject, grade=r.grade,
        question_key=r.question_key, question_text=r.question_text,
        standard_answer=r.standard_answer, question_type=r.question_type,
        max_score=float(r.max_score),
    ))


@router.post("", response_model=APIResponse[StandardAnswerOut])
def create_answer(body: StandardAnswerCreate, db: Session = Depends(get_db)):
    """新增标准答案"""
    exists = db.query(StandardAnswer).filter(
        StandardAnswer.question_key == body.question_key
    ).first()
    if exists:
        raise HTTPException(status_code=400, detail=f"question_key 重复: {body.question_key}")

    r = StandardAnswer(
        subject=body.subject, grade=body.grade,
        question_key=body.question_key, question_text=body.question_text,
        standard_answer=body.standard_answer, question_type=body.question_type,
        max_score=body.max_score,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    logger.info(f"新增标准答案: {r.question_key}")
    return APIResponse(data=StandardAnswerOut(
        id=r.id, subject=r.subject, grade=r.grade,
        question_key=r.question_key, question_text=r.question_text,
        standard_answer=r.standard_answer, question_type=r.question_type,
        max_score=float(r.max_score),
    ))


@router.put("/{answer_id}", response_model=APIResponse[StandardAnswerOut])
def update_answer(answer_id: int, body: StandardAnswerUpdate, db: Session = Depends(get_db)):
    """更新标准答案"""
    r = db.query(StandardAnswer).filter(StandardAnswer.id == answer_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="标准答案不存在")
    for field in ("subject", "grade", "question_text", "standard_answer", "question_type"):
        val = getattr(body, field, None)
        if val is not None:
            setattr(r, field, val)
    if body.max_score is not None:
        r.max_score = body.max_score
    db.commit()
    db.refresh(r)
    return APIResponse(data=StandardAnswerOut(
        id=r.id, subject=r.subject, grade=r.grade,
        question_key=r.question_key, question_text=r.question_text,
        standard_answer=r.standard_answer, question_type=r.question_type,
        max_score=float(r.max_score),
    ))


@router.delete("/{answer_id}", response_model=APIResponse)
def delete_answer(answer_id: int, db: Session = Depends(get_db)):
    """删除标准答案"""
    r = db.query(StandardAnswer).filter(StandardAnswer.id == answer_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="标准答案不存在")
    db.delete(r)
    db.commit()
    logger.info(f"删除标准答案: id={answer_id}, key={r.question_key}")
    return APIResponse(message="删除成功")


@router.post("/batch", response_model=APIResponse)
def batch_create(answers: List[StandardAnswerCreate], db: Session = Depends(get_db)):
    """批量导入标准答案"""
    inserted, skipped = 0, 0
    for body in answers:
        exists = db.query(StandardAnswer).filter(
            StandardAnswer.question_key == body.question_key
        ).first()
        if exists:
            skipped += 1
            continue
        db.add(StandardAnswer(
            subject=body.subject, grade=body.grade,
            question_key=body.question_key, question_text=body.question_text,
            standard_answer=body.standard_answer, question_type=body.question_type,
            max_score=body.max_score,
        ))
        inserted += 1
    db.commit()
    logger.info(f"批量导入标准答案: {inserted} 条新增, {skipped} 条跳过")
    return APIResponse(data={"inserted": inserted, "skipped": skipped})
