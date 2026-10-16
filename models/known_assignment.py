"""013-V01 geometry and recognition evidence; grades remain in GradingResult."""
from datetime import datetime
from sqlalchemy import BigInteger, Integer, String, Text, JSON, ForeignKey, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base

ID = BigInteger().with_variant(Integer, "sqlite")


class PageTemplate(Base):
    __tablename__ = "known_page_template"
    __table_args__ = (UniqueConstraint("page_uid", name="uq_known_page_uid"),)
    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    assignment_id: Mapped[int] = mapped_column(ID, ForeignKey("assignment.id"), index=True)
    variant_id: Mapped[int] = mapped_column(ID, ForeignKey("assignment_variant.id"), index=True)
    page_index: Mapped[int] = mapped_column(Integer)
    page_uid: Mapped[str] = mapped_column(String(40))
    export_version: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    image_locator: Mapped[str] = mapped_column(String(512))
    image_sha256: Mapped[str] = mapped_column(String(64))
    pdf_locator: Mapped[str | None] = mapped_column(String(512), nullable=True)
    variant_fingerprint: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    created_by: Mapped[int] = mapped_column(ID, ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class QuestionPlacement(Base):
    __tablename__ = "known_question_placement"
    __table_args__ = (UniqueConstraint("page_template_id", "variant_question_id", name="uq_known_placement"),)
    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    page_template_id: Mapped[int] = mapped_column(ID, ForeignKey("known_page_template.id"), index=True)
    variant_question_id: Mapped[int] = mapped_column(ID, ForeignKey("assignment_variant_question.id"))
    question_asset_id: Mapped[int | None] = mapped_column(ID, ForeignKey("question_asset.id"), nullable=True)
    question_number: Mapped[str] = mapped_column(String(20))
    stem_bbox: Mapped[list] = mapped_column(JSON)
    answer_bracket_bbox: Mapped[list] = mapped_column(JSON)
    options_bbox: Mapped[list | None] = mapped_column(JSON, nullable=True)
    question_bbox: Mapped[list] = mapped_column(JSON)
    choice_kind: Mapped[str] = mapped_column(String(10), default="single")


class KnownPageMatch(Base):
    __tablename__ = "known_page_match"
    __table_args__ = (UniqueConstraint("task_id", "homework_image_id", name="uq_known_task_image"),)
    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), ForeignKey("homework_task.task_id"), index=True)
    homework_image_id: Mapped[int] = mapped_column(ID, ForeignKey("homework_image.id"))
    page_template_id: Mapped[int | None] = mapped_column(ID, ForeignKey("known_page_template.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(24))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[dict] = mapped_column(JSON)
    aligned_locator: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ChoiceRead(Base):
    __tablename__ = "known_choice_read"
    __table_args__ = (UniqueConstraint("task_id", "placement_id", name="uq_known_task_placement"),)
    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), ForeignKey("homework_task.task_id"), index=True)
    page_match_id: Mapped[int] = mapped_column(ID, ForeignKey("known_page_match.id"))
    placement_id: Mapped[int] = mapped_column(ID, ForeignKey("known_question_placement.id"))
    symbol: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24), default="HOLD_REVIEW")
    reason: Mapped[str] = mapped_column(String(200))
    evidence_json: Mapped[dict] = mapped_column(JSON)
    crop_locator: Mapped[str] = mapped_column(String(512))
    ink_locator: Mapped[str] = mapped_column(String(512))
    grading_result_id: Mapped[int | None] = mapped_column(ID, ForeignKey("grading_result.id"), nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ID, ForeignKey("user.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ChoiceReviewAudit(Base):
    __tablename__ = "known_choice_review_audit"
    __table_args__ = (UniqueConstraint("choice_read_id", "request_key", name="uq_known_review_key"),)
    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    choice_read_id: Mapped[int] = mapped_column(ID, ForeignKey("known_choice_read.id"))
    request_key: Mapped[str] = mapped_column(String(64))
    reviewer_id: Mapped[int] = mapped_column(ID, ForeignKey("user.id"))
    before_json: Mapped[dict] = mapped_column(JSON)
    after_json: Mapped[dict] = mapped_column(JSON)
    note: Mapped[str] = mapped_column(Text)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
