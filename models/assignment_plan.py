"""013 teacher-owned assignment plans and immutable selected-question snapshots."""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
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

from .base import Base


_ID = BigInteger().with_variant(Integer, "sqlite")


class AssignmentPlan(Base):
    __tablename__ = "assignment_plan"
    __table_args__ = (
        UniqueConstraint("teacher_user_id", "idempotency_key", name="uq_assignment_plan_teacher_key"),
        Index("ix_assignment_plan_teacher_status", "teacher_user_id", "status"),
        Index("ix_assignment_plan_class_created", "class_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(_ID, primary_key=True, autoincrement=True)
    teacher_user_id: Mapped[int] = mapped_column(_ID, ForeignKey("user.id", ondelete="RESTRICT"), nullable=False)
    class_id: Mapped[int] = mapped_column(_ID, ForeignKey("classroom.id", ondelete="RESTRICT"), nullable=False)
    assignment_id: Mapped[int | None] = mapped_column(
        _ID, ForeignKey("assignment.id", ondelete="RESTRICT"), nullable=True, unique=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject: Mapped[str] = mapped_column(String(40), nullable=False)
    grade: Mapped[str] = mapped_column(String(40), nullable=False)
    assignment_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    target_knowledge_points_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    question_types_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    requested_question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    difficulty: Mapped[str | None] = mapped_column(String(20), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tier_strategy_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="MANUAL")
    source_provider: Mapped[str] = mapped_column(String(80), nullable=False)
    source_version: Mapped[str] = mapped_column(String(40), nullable=False)
    source_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="DRAFT", server_default="DRAFT")
    confirmed_by: Mapped[int | None] = mapped_column(_ID, ForeignKey("user.id", ondelete="RESTRICT"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AssignmentPlanQuestion(Base):
    __tablename__ = "assignment_plan_question"
    __table_args__ = (
        UniqueConstraint("plan_id", "level", "sort_order", name="uq_plan_question_order"),
        UniqueConstraint("plan_id", "level", "source_asset_id", name="uq_plan_question_asset"),
        Index("ix_assignment_plan_question_asset", "source_asset_id"),
    )

    id: Mapped[int] = mapped_column(_ID, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(
        _ID, ForeignKey("assignment_plan.id", ondelete="CASCADE"), nullable=False
    )
    level: Mapped[str] = mapped_column(String(2), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    source_asset_id: Mapped[int] = mapped_column(
        _ID, ForeignKey("question_asset.id", ondelete="RESTRICT"), nullable=False
    )
    question_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    max_score: Mapped[int] = mapped_column(Integer, nullable=False, default=10)

