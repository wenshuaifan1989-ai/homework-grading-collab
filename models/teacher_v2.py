"""Additive V2 aggregates; legacy AssignmentVariant is retained, not relabelled."""
from datetime import datetime
from sqlalchemy import BigInteger, Integer, String, Text, JSON, DateTime, ForeignKey, UniqueConstraint, event, func
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base

ID = BigInteger().with_variant(Integer, 'sqlite')


class PaperBatch(Base):
    __tablename__ = 'v2_paper_batch'
    __table_args__ = (UniqueConstraint('teacher_id', 'request_key', name='uq_v2_batch_request'),)
    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    teacher_id: Mapped[int] = mapped_column(ID, ForeignKey('user.id'), index=True)
    request_key: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PaperDocument(Base):
    __tablename__ = 'v2_paper_document'
    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(ID, ForeignKey('v2_paper_batch.id'), index=True)
    teacher_id: Mapped[int] = mapped_column(ID, ForeignKey('user.id'), index=True)
    title: Mapped[str] = mapped_column(String(200))
    source_name: Mapped[str] = mapped_column(String(255))
    source_locator: Mapped[str] = mapped_column(String(512))
    source_sha256: Mapped[str] = mapped_column(String(64))
    source_format: Mapped[str] = mapped_column(String(16))
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    questions: Mapped[list] = mapped_column(JSON, default=list)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(24), default='DRAFT')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AssignmentPublication(Base):
    __tablename__ = 'v2_assignment_publication'
    __table_args__ = (UniqueConstraint('teacher_id', 'request_key', name='uq_v2_publish_request'),)
    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    assignment_id: Mapped[int] = mapped_column(ID, ForeignKey('assignment.id'), unique=True)
    paper_id: Mapped[int] = mapped_column(ID, ForeignKey('v2_paper_document.id'))
    teacher_id: Mapped[int] = mapped_column(ID, ForeignKey('user.id'))
    variant_id: Mapped[int] = mapped_column(ID, ForeignKey('assignment_variant.id'))
    mode: Mapped[str] = mapped_column(String(24), default='uniform_mixed')
    request_key: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    snapshot: Mapped[dict] = mapped_column(JSON)
    snapshot_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


@event.listens_for(AssignmentPublication, 'before_update')
@event.listens_for(AssignmentPublication, 'before_delete')
def immutable_publication(mapper, connection, target):
    raise ValueError('Published snapshots are immutable; create a new assignment instead')
