"""Request contracts for 013 teacher-authored assignment plans."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


PlanLevel = Literal["L1", "L2", "L3"]


class PlanQuestionSelection(BaseModel):
    source_asset_id: int = Field(gt=0)
    max_score: int = Field(default=10, gt=0, le=1000)


class PlanVariantSelection(BaseModel):
    level: PlanLevel
    questions: list[PlanQuestionSelection] = Field(min_length=1, max_length=100)


class AssignmentPlanCreate(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=64)
    class_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    subject: str = Field(min_length=1, max_length=40)
    grade: str = Field(min_length=1, max_length=40)
    assignment_date: date
    due_at: datetime | None = None
    target_knowledge_points: list[str] = Field(default_factory=list, max_length=40)
    question_types: list[str] = Field(default_factory=list, max_length=20)
    question_count_per_tier: int = Field(ge=1, le=100)
    difficulty: Literal["easy", "medium", "hard", "mixed"] = "mixed"
    duration_minutes: int | None = Field(default=None, ge=1, le=600)
    tier_strategy: dict[str, str]
    variants: list[PlanVariantSelection] = Field(min_length=3, max_length=3)

    @field_validator("subject")
    @classmethod
    def normalize_subject(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned:
            raise ValueError("学科不能为空")
        return cleaned

    @field_validator("grade")
    @classmethod
    def normalize_grade(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned:
            raise ValueError("年级不能为空")
        return cleaned

    @model_validator(mode="after")
    def validate_plan_contract(self):
        levels = [variant.level for variant in self.variants]
        if set(levels) != {"L1", "L2", "L3"} or len(levels) != 3:
            raise ValueError("必须分别提供 L1、L2、L3 三个非空版本")
        if any(len(variant.questions) != self.question_count_per_tier for variant in self.variants):
            raise ValueError("每个层级的选题数量必须等于计划题数")
        if set(self.tier_strategy) != {"L1", "L2", "L3"} or any(
            not self.tier_strategy[level].strip() for level in ("L1", "L2", "L3")
        ):
            raise ValueError("必须明确填写 L1/L2/L3 三层策略")
        for variant in self.variants:
            ids = [item.source_asset_id for item in variant.questions]
            if len(ids) != len(set(ids)):
                raise ValueError(f"{variant.level} 版本内不能重复选择同一题")
        points = [value.strip() for value in self.target_knowledge_points]
        if any(not value for value in points) or len(points) != len(set(points)):
            raise ValueError("知识点不能为空或重复")
        self.target_knowledge_points = points
        return self


class AIPlanPromptRequest(BaseModel):
    class_id: int = Field(gt=0)
    subject: str = Field(min_length=1, max_length=40)
    grade: str = Field(min_length=1, max_length=40)
    prompt: str = Field(min_length=10, max_length=5000)
