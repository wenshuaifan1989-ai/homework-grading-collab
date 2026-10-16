from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from utils.phone import normalize_phone


class ClassCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    school_id: Optional[int] = Field(default=None, gt=0)
    academic_year: Optional[str] = Field(default=None, max_length=20)
    semester: Optional[str] = Field(default=None, max_length=20)
    grade: Optional[str] = Field(default=None, max_length=20)


class ClassJoinRequest(BaseModel):
    invite_code: str = Field(min_length=4, max_length=12)


class AssignmentCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    subject: str = Field(default="math", min_length=1, max_length=20)
    grade: str = Field(default="grade7", min_length=1, max_length=20)
    assignment_date: Optional[date] = None
    due_at: Optional[datetime] = None


class TeacherCreateRequest(BaseModel):
    phone: str
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=1, max_length=100)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        return normalize_phone(value)

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("密码 UTF-8 长度不能超过 72 字节")
        return value

    @field_validator("full_name")
    @classmethod
    def clean_full_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("教师姓名不能为空")
        return name


class AccountStatusRequest(BaseModel):
    is_active: bool


class PasswordResetRequest(BaseModel):
    password: str = Field(min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("密码 UTF-8 长度不能超过 72 字节")
        return value


class StudentRosterCreateRequest(BaseModel):
    student_name: str = Field(min_length=1, max_length=100)
    student_no: Optional[str] = Field(default=None, max_length=50)

    @field_validator("student_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("学生姓名不能为空")
        return name

    @field_validator("student_no")
    @classmethod
    def clean_student_no(cls, value: Optional[str]) -> Optional[str]:
        number = value.strip() if value else None
        return number or None


class StudentRosterBatchRequest(BaseModel):
    lines: str = Field(min_length=1, max_length=20000)


class StudentBindingOptionsRequest(BaseModel):
    invite_code: str = Field(min_length=4, max_length=12)
    student_name: Optional[str] = Field(default=None, max_length=100)


class StudentBindingRequest(StudentBindingOptionsRequest):
    roster_id: int = Field(gt=0)
