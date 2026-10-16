from pydantic import BaseModel, Field


class QuestionAssetReview(BaseModel):
    grading_result_id: int
    x1: int | None = None
    y1: int | None = None
    x2: int | None = None
    y2: int | None = None
    question_no: str | None = Field(default=None, max_length=40)
    question_text: str = Field(default="", max_length=12000)
    question_type: str | None = Field(default=None, max_length=80)
    options: list | dict | None = None
    correct_answer: str | None = Field(default=None, max_length=6000)
    analysis: str | None = Field(default=None, max_length=12000)
    difficulty: str | None = Field(default=None, max_length=20)
    knowledge_points: list[str] = Field(default_factory=list, max_length=40)
    manual_wrong: bool | None = None
    confirm: bool = True


class CorrectionSubmission(BaseModel):
    answer: str = Field(min_length=1, max_length=12000)
    note: str | None = Field(default=None, max_length=2000)


class MasterySubmission(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class CorrectionReview(BaseModel):
    accepted: bool
    feedback: str | None = Field(default=None, max_length=2000)
