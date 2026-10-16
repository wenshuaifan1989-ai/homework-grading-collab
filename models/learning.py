"""012 subject tiers and per-assignment differentiated variants."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    DECIMAL,
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
_LEVELS = "'L1','L2','L3'"


class StudentSubjectTier(Base):
    __tablename__ = "student_subject_tier"
    __table_args__ = (
        UniqueConstraint("student_id", "class_id", "subject", name="uq_student_class_subject_tier"),
        CheckConstraint(f"level IN ({_LEVELS})", name="ck_student_subject_tier_level"),
        Index("ix_student_subject_tier_class_subject", "class_id", "subject"),
    )

    id: Mapped[int] = mapped_column(_ID, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        _ID, ForeignKey("student.id", ondelete="CASCADE"), nullable=False
    )
    class_id: Mapped[int] = mapped_column(
        _ID, ForeignKey("classroom.id", ondelete="CASCADE"), nullable=False
    )
    subject: Mapped[str] = mapped_column(String(40), nullable=False)
    level: Mapped[str] = mapped_column(String(2), nullable=False)
    updated_by: Mapped[int] = mapped_column(_ID, ForeignKey("user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class StudentSubjectTierAudit(Base):
    __tablename__ = "student_subject_tier_audit"
    __table_args__ = (
        CheckConstraint(f"to_level IN ({_LEVELS})", name="ck_student_subject_tier_audit_to_level"),
        Index("ix_student_subject_tier_audit_student", "student_id", "class_id", "subject", "changed_at"),
    )

    id: Mapped[int] = mapped_column(_ID, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(_ID, ForeignKey("student.id", ondelete="CASCADE"), nullable=False)
    class_id: Mapped[int] = mapped_column(_ID, ForeignKey("classroom.id", ondelete="CASCADE"), nullable=False)
    subject: Mapped[str] = mapped_column(String(40), nullable=False)
    from_level: Mapped[str | None] = mapped_column(String(2), nullable=True)
    to_level: Mapped[str] = mapped_column(String(2), nullable=False)
    actor_user_id: Mapped[int] = mapped_column(_ID, ForeignKey("user.id"), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class AssignmentVariantSet(Base):
    __tablename__ = "assignment_variant_set"
    __table_args__ = (
        UniqueConstraint("assignment_id", name="uq_assignment_variant_set_assignment"),
        CheckConstraint(
            f"fallback_level IS NULL OR fallback_level IN ({_LEVELS})",
            name="ck_assignment_variant_set_fallback_level",
        ),
        CheckConstraint(
            f"allow_uniform_fallback = 0 OR fallback_level IN ({_LEVELS})",
            name="ck_assignment_variant_set_fallback_choice",
        ),
    )

    id: Mapped[int] = mapped_column(_ID, primary_key=True, autoincrement=True)
    assignment_id: Mapped[int] = mapped_column(
        _ID, ForeignKey("assignment.id", ondelete="CASCADE"), nullable=False
    )
    allow_uniform_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    fallback_level: Mapped[str | None] = mapped_column(String(2), nullable=True)
    updated_by: Mapped[int] = mapped_column(_ID, ForeignKey("user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AssignmentVariant(Base):
    __tablename__ = "assignment_variant"
    __table_args__ = (
        UniqueConstraint("assignment_id", "level", "version", name="uq_assignment_variant_version"),
        CheckConstraint(f"level IN ({_LEVELS})", name="ck_assignment_variant_level"),
        Index("ix_assignment_variant_current", "assignment_id", "is_current"),
    )

    id: Mapped[int] = mapped_column(_ID, primary_key=True, autoincrement=True)
    assignment_id: Mapped[int] = mapped_column(
        _ID, ForeignKey("assignment.id", ondelete="CASCADE"), nullable=False
    )
    level: Mapped[str] = mapped_column(String(2), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    updated_by: Mapped[int] = mapped_column(_ID, ForeignKey("user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class AssignmentVariantQuestion(Base):
    __tablename__ = "assignment_variant_question"
    __table_args__ = (
        UniqueConstraint("variant_id", "sort_order", name="uq_assignment_variant_question_order"),
        Index("ix_assignment_variant_question_asset", "source_asset_id"),
    )

    id: Mapped[int] = mapped_column(_ID, primary_key=True, autoincrement=True)
    variant_id: Mapped[int] = mapped_column(
        _ID, ForeignKey("assignment_variant.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(12), nullable=False)
    source_asset_id: Mapped[int | None] = mapped_column(
        _ID, ForeignKey("question_asset.id", ondelete="RESTRICT"), nullable=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    options_json: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    correct_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_score: Mapped[float] = mapped_column(DECIMAL(7, 2), nullable=False, default=10)


class AssignmentVariantTask(Base):
    """Server-chosen variant snapshot linked to a real submission task."""

    __tablename__ = "assignment_variant_task"
    __table_args__ = (
        UniqueConstraint("task_id", name="uq_assignment_variant_task_task"),
        Index("ix_assignment_variant_task_student", "assignment_id", "student_id"),
    )

    id: Mapped[int] = mapped_column(_ID, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("homework_task.task_id", ondelete="CASCADE"), nullable=False
    )
    assignment_id: Mapped[int] = mapped_column(
        _ID, ForeignKey("assignment.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[int] = mapped_column(_ID, ForeignKey("student.id", ondelete="CASCADE"), nullable=False)
    variant_id: Mapped[int] = mapped_column(
        _ID, ForeignKey("assignment_variant.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
