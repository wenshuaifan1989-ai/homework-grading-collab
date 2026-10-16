from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Attributes(Strict):
    subject: str | None = Field(None, max_length=40)
    grade: str | None = Field(None, max_length=40)
    difficulty: Literal['easy', 'medium', 'hard'] | None = None
    knowledge_points: list[str] | None = Field(None, max_length=40)
    catalog_version: str | None = Field(None, max_length=100)
    question_type: str | None = Field(None, max_length=80)


class PaperQuestion(Strict):
    asset_id: int = Field(gt=0)
    number: str = Field(min_length=1, max_length=20)
    max_score: int = Field(10, ge=1, le=999)
    overrides: Attributes = Field(default_factory=Attributes)


class PaperEdit(Strict):
    expected_revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    attributes: Attributes = Field(default_factory=Attributes)
    questions: list[PaperQuestion] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def unique_questions(self):
        if len({q.number for q in self.questions}) != len(self.questions):
            raise ValueError('题号不能重复')
        if len({q.asset_id for q in self.questions}) != len(self.questions):
            raise ValueError('同一套卷不能重复关联同一题目')
        return self


class Requirement(Strict):
    student_id: int = Field(gt=0)
    number: str = Field(min_length=1, max_length=20)
    requirement: Literal['required', 'optional']
    reason: str = Field(min_length=1, max_length=500)


class Publish(Strict):
    request_key: str = Field(min_length=8, max_length=64)
    expected_revision: int = Field(ge=1)
    class_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=200)
    assignment_date: date
    due_at: datetime | None = None
    confirmed: Literal[True]
    default_requirement: Literal['required', 'optional'] = 'required'
    requirements: list[Requirement] = Field(default_factory=list, max_length=10000)

    @model_validator(mode='after')
    def unique_requirements(self):
        keys = [(r.student_id, r.number) for r in self.requirements]
        if len(keys) != len(set(keys)):
            raise ValueError('学生题目要求重复')
        return self
