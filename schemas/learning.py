"""Request schemas for 012 subject tiers and assignment variants."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


LearningLevel = Literal["L1", "L2", "L3"]


class StudentTierChange(BaseModel):
    student_id: int = Field(gt=0)
    level: LearningLevel


class SubjectTierBatchRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=40)
    entries: list[StudentTierChange] = Field(min_length=1, max_length=1000)

    @field_validator("subject")
    @classmethod
    def normalize_subject(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned or not cleaned[0].isalpha():
            raise ValueError("学科标识无效")
        if any(not (char.isalnum() or char in "_-") for char in cleaned):
            raise ValueError("学科标识无效")
        return cleaned

    @model_validator(mode="after")
    def unique_students(self):
        ids = [entry.student_id for entry in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("同一批次不能重复设置同一学生")
        return self


class VariantQuestionInput(BaseModel):
    source_asset_id: int | None = Field(default=None, gt=0)
    question_text: str | None = Field(default=None, max_length=12000)
    options: list[str] | dict[str, str] | None = None
    correct_answer: str | None = Field(default=None, max_length=4000)
    analysis: str | None = Field(default=None, max_length=8000)
    max_score: float = Field(default=10, gt=0, le=1000)

    @model_validator(mode="after")
    def require_one_source(self):
        has_asset = self.source_asset_id is not None
        has_manual_text = bool(self.question_text and self.question_text.strip())
        if has_asset == has_manual_text:
            raise ValueError("每道题必须且只能指定一个已确认题目资产或教师录入题面")
        if has_manual_text:
            self.question_text = self.question_text.strip()
        return self


class AssignmentVariantInput(BaseModel):
    level: LearningLevel
    questions: list[VariantQuestionInput] = Field(min_length=1, max_length=100)


class AssignmentVariantsUpsertRequest(BaseModel):
    variants: list[AssignmentVariantInput] = Field(min_length=3, max_length=3)
    allow_uniform_fallback: bool = False
    uniform_fallback_level: LearningLevel | None = None

    @model_validator(mode="after")
    def validate_three_tiers_and_fallback(self):
        levels = [variant.level for variant in self.variants]
        if set(levels) != {"L1", "L2", "L3"} or len(levels) != 3:
            raise ValueError("必须分别提供 L1、L2、L3 三个版本")
        if self.allow_uniform_fallback and self.uniform_fallback_level is None:
            raise ValueError("启用统一作业降级时必须明确选择统一版本")
        if not self.allow_uniform_fallback and self.uniform_fallback_level is not None:
            raise ValueError("未启用统一作业降级时不能指定统一版本")
        return self
