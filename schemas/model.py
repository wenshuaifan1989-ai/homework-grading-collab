from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class ModelInfo(BaseModel):
    """前端可见的模型信息（不暴露 API Key）"""
    name: str
    provider: str
    type: str          # text | vision
    model_id: str
    enabled: bool


class ModelsResponse(BaseModel):
    models: List[ModelInfo]


class ConfigResponse(BaseModel):
    grading_mode: str
    ocr_enabled: bool
    models_count: int
    upload_limits: Dict[str, Any]
    app_name: str
    app_version: str


class AnalyzeResult(BaseModel):
    """单题分析结果（不含评分）"""
    question_no: str
    question_text: Optional[str] = None
    student_answer: Optional[str] = None
    question_type: Optional[str] = None
    position: Optional[dict] = None   # {"x1", "y1", "x2", "y2"}


class AnalyzeResponse(BaseModel):
    task_id: str
    questions: List[AnalyzeResult]
    mode: str  # ocr | vision


class ModelToggleRequest(BaseModel):
    """模型启用/禁用请求"""
    enabled: bool
