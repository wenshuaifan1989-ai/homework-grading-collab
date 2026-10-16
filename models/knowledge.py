from sqlalchemy import BigInteger, String, Text, DECIMAL
from sqlalchemy.orm import Mapped, mapped_column
from decimal import Decimal
from .base import BaseModel


class KnowledgePoint(BaseModel):
    """
    知识点表
    """

    __tablename__ = "knowledge_point"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    subject: Mapped[str] = mapped_column(String(20), nullable=False, comment="学科")
    grade: Mapped[str] = mapped_column(String(20), nullable=False, comment="年级")
    chapter: Mapped[str | None] = mapped_column(String(100), comment="章节")
    knowledge_point: Mapped[str] = mapped_column(String(200), nullable=False, comment="知识点")
    difficulty: Mapped[Decimal] = mapped_column(DECIMAL(2, 1), default=3.0, comment="难度系数")
    description: Mapped[str | None] = mapped_column(Text, comment="知识点描述")