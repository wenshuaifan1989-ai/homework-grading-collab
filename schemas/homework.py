from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    failure_code: Optional[str] = None
    failure_message: Optional[str] = None
    call_id: Optional[str] = None
    can_retry: bool = False


class HomeworkRetryRequest(BaseModel):
    confirm_possible_duplicate_charge: bool = False


class GradingResult(BaseModel):
    question_block_id: int
    question_no: str
    question_text: Optional[str] = None
    student_answer: Optional[str] = None
    question_type: Optional[str] = None
    score: float
    max_score: float
    accuracy: Optional[float] = None   # 正确率 0-100
    result: str
    comment: Optional[str] = None
    analysis: Optional[str] = None
    confidence: Optional[float] = None
    raw_response: Optional[Dict[str, Any]] = None
    # ---- G2 ----
    image_index: Optional[int] = None                 # 所属图片顺序(0起)
    correct_answer: Optional[str] = None              # 标准答案
    error_type: Optional[str] = None                  # 错因（正确题为空）
    knowledge_points: Optional[list] = None           # 知识点列表
    difficulty: Optional[str] = None                  # easy/medium/hard/unknown

    class Config:
        from_attributes = True


class GradingResultResponse(BaseModel):
    task_id: str
    status: Optional[str] = None                       # G2: 任务汇总状态
    image_count: Optional[int] = None                  # G2: 本次作业图片数
    total_score: float
    total_max_score: Optional[float] = None            # G2: 总满分
    total_accuracy: Optional[float] = None   # 整体正确率 0-100
    grading_mode: Optional[str] = None       # ocr | vision
    model_name: Optional[str] = None                   # G2: 批改模型可追溯
    prompt_version: Optional[str] = None               # G2: prompt 版本可追溯
    failed_image_index: Optional[int] = None           # G2: 失败图片定位
    total_questions: Optional[int] = None              # G2: 总题数
    correct_count: Optional[int] = None                # G2: 对题数
    partial_count: Optional[int] = None                # G2: 部分正确数
    wrong_count: Optional[int] = None                  # G2: 错题数
    images: Optional[list] = None                      # G2: 按顺序的图片摘要
    results: list[GradingResult]
    created_at: datetime


class HomeworkUploadRequest(BaseModel):
    subject: str
    grade: str
    user_id: int


class HomeworkListResponse(BaseModel):
    task_id: str
    subject: str
    grade: str
    user_id: int
    status: str
    created_at: datetime
    updated_at: datetime
