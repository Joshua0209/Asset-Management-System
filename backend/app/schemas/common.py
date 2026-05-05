from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DataResponse(APIModel, Generic[T]):
    data: T


class ListResponse(APIModel, Generic[T]):
    data: list[T]


class ErrorDetail(APIModel):
    field: str
    message: str
    code: str


class ErrorEnvelope(APIModel):
    code: str
    message: str
    details: list[ErrorDetail] | None = None


class ErrorResponse(APIModel):
    error: ErrorEnvelope


class PaginationMeta(APIModel):
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    per_page: int = Field(ge=1)
    total_pages: int = Field(ge=0)


class PaginatedListResponse(APIModel, Generic[T]):
    data: list[T]
    meta: PaginationMeta
