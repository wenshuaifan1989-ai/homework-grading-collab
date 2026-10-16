from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
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


class Student(Base):
    """Stable learner identity, independent from login accounts and roles."""

    __tablename__ = "student"

    id: Mapped[int] = mapped_column(_ID, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class StudentUserBinding(Base):
    __tablename__ = "student_user_binding"
    __table_args__ = (
        UniqueConstraint("student_id", "user_id", name="uq_student_user_binding_pair"),
        CheckConstraint(
            "relationship_type IN ('self','father','mother','paternal_grandfather',"
            "'paternal_grandmother','maternal_grandfather','maternal_grandmother',"
            "'guardian','other')",
            name="ck_student_user_binding_relationship_type",
        ),
        Index("ix_student_user_binding_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(_ID, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        _ID, ForeignKey("student.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        _ID, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(String(40), nullable=False)
    relationship_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ClassTeacher(Base):
    __tablename__ = "class_teacher"
    __table_args__ = (
        UniqueConstraint("class_id", "teacher_user_id", name="uq_class_teacher_pair"),
        Index("ix_class_teacher_user_status", "teacher_user_id", "status"),
    )

    id: Mapped[int] = mapped_column(_ID, primary_key=True, autoincrement=True)
    class_id: Mapped[int] = mapped_column(
        _ID, ForeignKey("classroom.id", ondelete="CASCADE"), nullable=False
    )
    teacher_user_id: Mapped[int] = mapped_column(
        _ID, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    subject_codes_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Contract(Base):
    __tablename__ = "contract"
    __table_args__ = (
        UniqueConstraint("code", name="uq_contract_code"),
        CheckConstraint(
            "type IN ('STUDENT_CLASS_JOIN','TEACHER_CLASS_JOIN','FAMILY_BIND')",
            name="ck_contract_type",
        ),
        Index("ix_contract_target_status", "type", "target_id", "status"),
    )

    id: Mapped[int] = mapped_column(_ID, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[int] = mapped_column(_ID, nullable=False)
    creator_user_id: Mapped[int] = mapped_column(
        _ID, ForeignKey("user.id"), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class School(Base):
    __tablename__ = "school"
    __table_args__ = (
        UniqueConstraint(
            "official_name", "province", "city", "district", "stage",
            name="uq_school_official_region_stage",
        ),
        Index("ix_school_stage_region", "stage", "province", "city", "district"),
        Index("ix_school_status_name", "status", "official_name"),
    )

    id: Mapped[int] = mapped_column(_ID, primary_key=True, autoincrement=True)
    official_name: Mapped[str] = mapped_column(String(200), nullable=False)
    province: Mapped[str | None] = mapped_column(String(50), nullable=True)
    city: Mapped[str | None] = mapped_column(String(50), nullable=True)
    district: Mapped[str | None] = mapped_column(String(50), nullable=True)
    stage: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="active", server_default="active"
    )
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_custom: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
