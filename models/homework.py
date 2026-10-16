from sqlalchemy import BigInteger, String, Text, DECIMAL, Boolean, ForeignKey, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from decimal import Decimal
from .base import BaseModel


class HomeworkTask(BaseModel):
    __tablename__ = "homework_task"
    
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    task_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="任务ID")
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id"), nullable=False, comment="用户ID"
    )
    subject: Mapped[str] = mapped_column(String(20), nullable=False, comment="学科")
    grade: Mapped[str] = mapped_column(String(20), nullable=False, comment="年级")
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDING",
        comment="任务状态：PENDING/PROCESSING/SUCCESS/FAILED",
    )
    total_score: Mapped[Decimal | None] = mapped_column(DECIMAL(5, 2), default=0, comment="总分")
    grading_mode: Mapped[str | None] = mapped_column(String(10), nullable=True, comment="批改模式: ocr/vision")
    error_message: Mapped[str | None] = mapped_column(Text, comment="错误信息")
    # ---- G2: 批改可追溯性 ----
    model_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="批改所用模型名（不记录任何密钥）"
    )
    prompt_version: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="批改 prompt 版本"
    )
    failed_image_index: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="多图任务失败时的图片顺序索引（0 起）"
    )
    assignment_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("assignment.id"), nullable=True, index=True
    )
    class_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("classroom.id"), nullable=True, index=True
    )
    student_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("student.id"), nullable=True, index=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user.id"), nullable=True, index=True
    )

    user = relationship(
        "User", back_populates="homework_tasks", foreign_keys=[user_id]
    )
    actor = relationship("User", foreign_keys=[actor_user_id])
    images = relationship(
        "HomeworkImage", back_populates="task", cascade="all, delete-orphan"
    )
    question_blocks = relationship(
        "QuestionBlock", back_populates="task", cascade="all, delete-orphan"
    )
    ocr_results = relationship(
        "OCRResult", back_populates="task", cascade="all, delete-orphan"
    )
    grading_results = relationship(
        "GradingResult", back_populates="task", cascade="all, delete-orphan"
    )


class HomeworkImage(BaseModel):
    __tablename__ = "homework_image"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    task_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("homework_task.task_id"),
        nullable=False,
        comment="任务ID",
    )
    original_url: Mapped[str] = mapped_column(String(255), nullable=False, comment="原始图片URL")
    processed_url: Mapped[str | None] = mapped_column(String(255), comment="预处理后图片URL")
    # ---- G2: 多图上传顺序（0 起，按上传顺序） ----
    image_index: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="图片顺序索引(0起)"
    )

    task = relationship("HomeworkTask", back_populates="images")


class QuestionBlock(BaseModel):
    __tablename__ = "question_block"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    task_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("homework_task.task_id"),
        nullable=False,
        comment="任务ID",
    )
    question_no: Mapped[str] = mapped_column(String(20), nullable=False, comment="题号")
    question_image_url: Mapped[str] = mapped_column(String(255), nullable=False, comment="题目图片URL")
    x1: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="左上角x坐标")
    y1: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="左上角y坐标")
    x2: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="右下角x坐标")
    y2: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="右下角y坐标")
    # ---- G2: 题目所属图片页（0 起），用于多图归属与跨页重复题号区分 ----
    image_index: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="所属图片顺序索引(0起)"
    )

    task = relationship("HomeworkTask", back_populates="question_blocks")
    ocr_result = relationship(
        "OCRResult", back_populates="question_block", uselist=False
    )
    grading_result = relationship(
        "GradingResult", back_populates="question_block", uselist=False
    )


class OCRResult(BaseModel):
    __tablename__ = "ocr_result"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    task_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("homework_task.task_id"),
        nullable=False,
        comment="任务ID",
    )
    question_block_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("question_block.id"), nullable=False, comment="题目块ID"
    )
    question_no: Mapped[str] = mapped_column(String(20), nullable=False, comment="题号")
    question_text: Mapped[str | None] = mapped_column(Text, comment="题干文本")
    student_answer: Mapped[str | None] = mapped_column(Text, comment="学生答案")
    question_type: Mapped[str | None] = mapped_column(String(50), comment="题型")
    raw_response: Mapped[dict | None] = mapped_column(JSON, comment="原始OCR响应")

    task = relationship("HomeworkTask", back_populates="ocr_results")
    question_block = relationship("QuestionBlock", back_populates="ocr_result")


class StandardAnswer(BaseModel):
    __tablename__ = "standard_answer"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    subject: Mapped[str] = mapped_column(String(20), nullable=False, comment="学科")
    grade: Mapped[str] = mapped_column(String(20), nullable=False, comment="年级")
    question_key: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, comment="题目唯一标识"
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False, comment="题干文本")
    standard_answer: Mapped[str] = mapped_column(Text, nullable=False, comment="标准答案")
    question_type: Mapped[str] = mapped_column(String(50), nullable=False, comment="题型")
    max_score: Mapped[Decimal] = mapped_column(DECIMAL(5, 2), nullable=False, comment="满分")


class GradingResult(BaseModel):
    __tablename__ = "grading_result"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    task_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("homework_task.task_id"),
        nullable=False,
        comment="任务ID",
    )
    question_block_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("question_block.id"), nullable=False, comment="题目块ID"
    )
    question_no: Mapped[str] = mapped_column(String(20), nullable=False, comment="题号")
    score: Mapped[Decimal] = mapped_column(DECIMAL(5, 2), nullable=False, comment="得分")
    max_score: Mapped[Decimal] = mapped_column(DECIMAL(5, 2), nullable=False, comment="满分")
    accuracy: Mapped[Decimal | None] = mapped_column(DECIMAL(5, 2), nullable=True, comment="正确率 0-100")
    result: Mapped[str] = mapped_column(String(20), nullable=False, comment="批改结果：正确/部分正确/错误")
    comment: Mapped[str | None] = mapped_column(Text, comment="批改批注")
    analysis: Mapped[str | None] = mapped_column(Text, comment="题目解析")
    confidence: Mapped[Decimal | None] = mapped_column(DECIMAL(3, 2), comment="模型置信度")
    is_reviewed: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已人工复核")
    reviewed_score: Mapped[Decimal | None] = mapped_column(DECIMAL(5, 2), comment="复核后得分")
    reviewer_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("user.id"), comment="复核人ID")
    raw_response: Mapped[dict | None] = mapped_column(JSON, comment="原始大模型响应")
    # ---- G2: 数据基础字段（供学生/班级面板、错因与知识点统计） ----
    correct_answer: Mapped[str | None] = mapped_column(Text, nullable=True, comment="标准答案")
    error_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="错因类型（正确题为空）"
    )
    knowledge_points: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="知识点列表(JSON list)"
    )
    difficulty: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="难度: easy/medium/hard/unknown"
    )

    task = relationship("HomeworkTask", back_populates="grading_results")
    question_block = relationship("QuestionBlock", back_populates="grading_result")
    reviewer = relationship("User", back_populates="reviewed_results")
