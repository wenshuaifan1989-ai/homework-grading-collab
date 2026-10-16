"""Additive paper-question assets and student mistake history for 011."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DECIMAL,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import BaseModel


_ID = BigInteger().with_variant(Integer, "sqlite")


class QuestionAsset(BaseModel):
    """Reusable structured question; each student's source evidence stays separate."""

    __tablename__ = "question_asset"
    __table_args__ = (
        UniqueConstraint("content_fingerprint", name="uq_question_asset_fingerprint"),
        Index("ix_question_asset_subject_grade", "subject", "grade"),
    )

    id: Mapped[int] = mapped_column(_ID, primary_key=True, autoincrement=True)
    subject: Mapped[str] = mapped_column(String(40), nullable=False)
    grade: Mapped[str] = mapped_column(String(40), nullable=False)
    question_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    question_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    options_json: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    correct_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    difficulty: Mapped[str | None] = mapped_column(String(20), nullable=True)
    knowledge_points_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float | None] = mapped_column(DECIMAL(4, 3), nullable=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="paper_digitization")
    asset_version: Mapped[str] = mapped_column(String(40), nullable=False, default="011-v1")
    rights_basis: Mapped[str | None] = mapped_column(String(80), nullable=True)
    rights_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    review_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="PENDING_REVIEW", server_default="PENDING_REVIEW"
    )
    clean_image_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="PENDING_REVIEW", server_default="PENDING_REVIEW"
    )
    content_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)


class QuestionAssetSource(BaseModel):
    """Immutable page/bbox/crop provenance for one student homework source."""

    __tablename__ = "question_asset_source"
    __table_args__ = (
        UniqueConstraint("source_task_id", "source_image_id", "page_index", "bbox_fingerprint",
                         name="uq_question_asset_source_bbox"),
        UniqueConstraint("grading_result_id", name="uq_question_asset_source_grading_result"),
        Index("ix_question_asset_source_task_page", "source_task_id", "page_index"),
    )

    id: Mapped[int] = mapped_column(_ID, primary_key=True, autoincrement=True)
    question_asset_id: Mapped[int] = mapped_column(
        _ID, ForeignKey("question_asset.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_task_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("homework_task.task_id", ondelete="RESTRICT"), nullable=False
    )
    source_image_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("homework_image.id", ondelete="RESTRICT"), nullable=False
    )
    grading_result_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("grading_result.id", ondelete="RESTRICT"), nullable=True
    )
    page_index: Mapped[int] = mapped_column(Integer, nullable=False)
    question_no: Mapped[str | None] = mapped_column(String(40), nullable=True)
    x1: Mapped[int] = mapped_column(Integer, nullable=False)
    y1: Mapped[int] = mapped_column(Integer, nullable=False)
    x2: Mapped[int] = mapped_column(Integer, nullable=False)
    y2: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    crop_locator: Mapped[str] = mapped_column(String(512), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_version: Mapped[str] = mapped_column(String(40), nullable=False)
    link_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="PENDING_REVIEW", server_default="PENDING_REVIEW"
    )
    review_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="PENDING_REVIEW", server_default="PENDING_REVIEW"
    )
    link_confidence: Mapped[float | None] = mapped_column(DECIMAL(4, 3), nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="RESTRICT"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class QuestionDigitizationRun(BaseModel):
    """Per-page record that prevents failed/empty cuts from being silently lost."""

    __tablename__ = "question_digitization_run"
    __table_args__ = (
        UniqueConstraint("source_image_id", "provider_version", name="uq_digitization_image_version"),
        Index("ix_digitization_task_status", "source_task_id", "status"),
    )

    id: Mapped[int] = mapped_column(_ID, primary_key=True, autoincrement=True)
    source_task_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("homework_task.task_id", ondelete="RESTRICT"), nullable=False
    )
    source_image_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("homework_image.id", ondelete="RESTRICT"), nullable=False
    )
    page_index: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_name: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class MistakeRecord(BaseModel):
    """A student-scoped wrong-question relation; never keyed by login User."""

    __tablename__ = "mistake_record"
    __table_args__ = (
        UniqueConstraint("student_id", "source_grading_result_id", name="uq_mistake_student_result"),
        Index("ix_mistake_student_created", "student_id", "created_at"),
        Index("ix_mistake_assignment_student", "assignment_id", "student_id"),
    )

    id: Mapped[int] = mapped_column(_ID, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        _ID, ForeignKey("student.id", ondelete="RESTRICT"), nullable=False
    )
    assignment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("assignment.id", ondelete="RESTRICT"), nullable=False
    )
    question_asset_id: Mapped[int] = mapped_column(
        _ID, ForeignKey("question_asset.id", ondelete="RESTRICT"), nullable=False
    )
    question_asset_source_id: Mapped[int] = mapped_column(
        _ID, ForeignKey("question_asset_source.id", ondelete="RESTRICT"), nullable=False
    )
    source_task_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("homework_task.task_id", ondelete="RESTRICT"), nullable=False
    )
    source_grading_result_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("grading_result.id", ondelete="RESTRICT"), nullable=False
    )
    detection_basis: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="open", server_default="open"
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class PaperCorrectionAttempt(BaseModel):
    """Append-only student correction/mastery history with teacher review metadata."""

    __tablename__ = "paper_correction_attempt"
    __table_args__ = (
        Index("ix_paper_correction_mistake_created", "mistake_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(_ID, primary_key=True, autoincrement=True)
    mistake_id: Mapped[int] = mapped_column(
        _ID, ForeignKey("mistake_record.id", ondelete="RESTRICT"), nullable=False
    )
    student_id: Mapped[int] = mapped_column(
        _ID, ForeignKey("student.id", ondelete="RESTRICT"), nullable=False
    )
    attempt_type: Mapped[str] = mapped_column(String(32), nullable=False)
    submitted_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    review_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="RESTRICT"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
