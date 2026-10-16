from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


_SHANGHAI = ZoneInfo("Asia/Shanghai")
_ID = BigInteger().with_variant(Integer, "sqlite")


def shanghai_today() -> date:
    return datetime.now(_SHANGHAI).date()


class Class(Base):
    __tablename__ = "classroom"

    id: Mapped[int] = mapped_column(_ID, primary_key=True, autoincrement=True)
    teacher_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id"), nullable=False, index=True
    )
    school_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("school.id"), nullable=True, index=True
    )
    academic_year: Mapped[str | None] = mapped_column(String(20), nullable=True)
    semester: Mapped[str | None] = mapped_column(String(20), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    invite_code: Mapped[str] = mapped_column(String(12), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class ClassMember(Base):
    __tablename__ = "class_member"
    __table_args__ = (
        UniqueConstraint(
            "class_id", "student_id", name="uq_class_member_class_student"
        ),
    )

    id: Mapped[int] = mapped_column(_ID, primary_key=True, autoincrement=True)
    class_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("classroom.id"), nullable=False, index=True
    )
    student_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id"), nullable=False, index=True
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class StudentRoster(Base):
    __tablename__ = "student_roster"
    __table_args__ = (
        UniqueConstraint("class_id", "student_no", name="uq_roster_class_student_no"),
        UniqueConstraint("bound_user_id", name="uq_roster_bound_user"),
    )

    id: Mapped[int] = mapped_column(_ID, primary_key=True, autoincrement=True)
    class_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("classroom.id"), nullable=False, index=True
    )
    student_name: Mapped[str] = mapped_column(String(100), nullable=False)
    student_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bound_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user.id"), nullable=True, index=True
    )
    student_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("student.id"), nullable=True, index=True
    )
    disambiguation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Assignment(Base):
    __tablename__ = "assignment"
    __table_args__ = (
        Index("ix_assignment_class_assignment_date", "class_id", "assignment_date"),
    )

    id: Mapped[int] = mapped_column(_ID, primary_key=True, autoincrement=True)
    class_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("classroom.id"), nullable=False, index=True
    )
    teacher_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject: Mapped[str] = mapped_column(
        String(20), nullable=False, default="math", server_default="math"
    )
    grade: Mapped[str] = mapped_column(
        String(20), nullable=False, default="grade7", server_default="grade7"
    )
    assignment_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        default=shanghai_today,
        server_default=text("(CURRENT_DATE)"),
        comment="教学归档日期（Asia/Shanghai）",
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="published", server_default="published"
    )
