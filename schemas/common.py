from typing import Generic, TypeVar, Optional, Any
from pydantic import BaseModel

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    code: int = 200
    message: str = "success"
    data: Optional[T] = None

    class Config:
        from_attributes = True


class PageInfo(BaseModel):
    page: int = 1
    page_size: int = 20
    total: int = 0


class PageResponse(BaseModel, Generic[T]):
    items: list[T]
    page_info: PageInfo
