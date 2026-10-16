from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from typing import Optional
from datetime import datetime

from utils.phone import normalize_phone

"""
BaseModel
    ├── UserBase           (基础用户信息)
    │       ├── UserCreate (创建用户)
    │       └── UserResponse (响应用户信息)
    │
    ├── UserUpdate         (更新用户)
    ├── LoginRequest       (登录请求)
    └── TokenResponse      (登录响应)
"""


class UserBase(BaseModel):
    username: str
    email: EmailStr
    role: str = "student"


class UserCreate(UserBase):
    password: str


class UserRegisterRequest(BaseModel):
    phone: str
    password: str = Field(min_length=8, max_length=72)
    full_name: Optional[str] = Field(default=None, max_length=100)
    email: Optional[EmailStr] = None
    role: Optional[str] = None

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


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = None


class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    phone: Optional[str] = None
    full_name: Optional[str] = None
    bind_status: Optional[str] = None
    bound_class_id: Optional[int] = None
    bound_class_name: Optional[str] = None
    roster_id: Optional[int] = None
    student_name: Optional[str] = None
    student_no: Optional[str] = None
    roles: list[str] = Field(default_factory=list)
    wechat_bind_status: str = "unbound"
    phone_source: Optional[str] = None
    profile_complete: bool = False

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    identifier: Optional[str] = Field(default=None, min_length=1, max_length=100)
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    password: str

    @field_validator("identifier")
    @classmethod
    def normalize_identifier(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value is not None else value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: Optional[str]) -> Optional[str]:
        return normalize_phone(value) if value else value

    @model_validator(mode="after")
    def require_one_login_identifier(self):
        identifiers = (self.identifier, self.phone, self.email)
        if sum(bool(value) for value in identifiers) != 1:
            raise ValueError("登录账号必须且只能填写一个")
        return self


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class WechatLoginRequest(BaseModel):
    code: str = Field(min_length=1, max_length=512)


class WechatPhoneRequest(BaseModel):
    code: str = Field(min_length=1, max_length=512)


class UserProfilePatch(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=100)
    phone: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: Optional[str]) -> Optional[str]:
        return normalize_phone(value) if value else value

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value is not None else value
