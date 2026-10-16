from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class BaseModel(Base):
    __abstract__ = True

    created_at: Mapped[DateTime] = mapped_column(
        DateTime, default=func.now(), nullable=False, comment="创建时间"
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="更新时间",
    )