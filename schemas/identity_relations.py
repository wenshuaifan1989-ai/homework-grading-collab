from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


RelationshipType = Literal[
    "self",
    "father",
    "mother",
    "paternal_grandfather",
    "paternal_grandmother",
    "maternal_grandfather",
    "maternal_grandmother",
    "guardian",
    "other",
]


class ContractCreateRequest(BaseModel):
    type: Literal["STUDENT_CLASS_JOIN", "TEACHER_CLASS_JOIN"]
    expires_at: datetime | None = None
    max_uses: int | None = Field(default=None, ge=1, le=1000)


class ContractClaimRequest(BaseModel):
    student_id: int | None = Field(default=None, gt=0)
    student_name: str | None = Field(default=None, max_length=100)
    roster_id: int | None = Field(default=None, gt=0)
    relationship_type: RelationshipType | None = None
    relationship_label: str | None = Field(default=None, max_length=80)
    subject_codes: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("student_name")
    @classmethod
    def clean_student_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("学生姓名不能为空")
        return value

    @field_validator("subject_codes")
    @classmethod
    def clean_subject_codes(cls, values: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if any(len(value) > 30 for value in cleaned):
            raise ValueError("学科代码不能超过 30 个字符")
        return cleaned


class RelationshipReviewRequest(BaseModel):
    approve: bool


class ClassStatusRequest(BaseModel):
    status: Literal["active", "archived", "dissolved"]


class OwnerTransferRequest(BaseModel):
    teacher_user_id: int = Field(gt=0)


class StudentLeaveReviewRequest(BaseModel):
    approve: bool


class SchoolCreateRequest(BaseModel):
    official_name: str = Field(min_length=1, max_length=200)
    province: str | None = Field(default=None, max_length=50)
    city: str | None = Field(default=None, max_length=50)
    district: str | None = Field(default=None, max_length=50)
    stage: str | None = Field(default=None, max_length=30)

    @field_validator("official_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("学校名称不能为空")
        return name


class SchoolImportRequest(BaseModel):
    official_name: str = Field(min_length=1, max_length=200)
    province: str | None = Field(default=None, max_length=50)
    city: str | None = Field(default=None, max_length=50)
    district: str | None = Field(default=None, max_length=50)
    stage: str | None = Field(default=None, max_length=30)
    source: str = Field(min_length=1, max_length=200)


class PlatformUserStatusRequest(BaseModel):
    is_active: bool


class StudentRelationCorrectionRequest(BaseModel):
    user_id: int = Field(gt=0)
    relationship_type: RelationshipType
    relationship_label: str | None = Field(default=None, max_length=80)
    status: Literal["active", "revoked", "pending_review"] = "active"


class RosterStudentCorrectionRequest(BaseModel):
    student_id: int | None = Field(default=None, gt=0)
