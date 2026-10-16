"""Idempotency records for multipart homework uploads."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class HomeworkSubmissionKey(Base):
    __tablename__ = "homework_submission_key"
    __table_args__ = (
        UniqueConstraint("user_id", "request_key", name="uq_homework_submission_user_key"),
        UniqueConstraint("task_id", name="uq_homework_submission_task_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    request_key: Mapped[str] = mapped_column(String(64), nullable=False)
    # Deliberately not an FK: this is written before upload persistence to make
    # concurrent retries observable and may outlive a failed/incomplete upload.
    task_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PROCESSING")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
