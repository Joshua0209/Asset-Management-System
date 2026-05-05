from __future__ import annotations

import math
from typing import Annotated, Any, Generic, TypeVar

from fastapi import Path
from pydantic import BaseModel, ConfigDict, Field, computed_field

T = TypeVar("T")

UUID_PATTERN = (
    r"^[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}$"
)

# `str` (not `uuid.UUID`) because IDs are stored as CHAR(36) in MySQL and
# SQLAlchemy returns them as strings; round-tripping through UUID would force
# coercion at every layer with no real safety gain. The regex enforces shape
# at the JSON boundary; `json_schema_extra` makes OpenAPI emit `format: uuid`.
UUIDString = Annotated[str, Field(pattern=UUID_PATTERN, json_schema_extra={"format": "uuid"})]
UUIDPath = Annotated[str, Path(pattern=UUID_PATTERN, json_schema_extra={"format": "uuid"})]


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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_pages(self) -> int:
        # Derived rather than stored so endpoints can't drift from
        # `ceil(total / per_page)`. Empty pages collapse to 0 so the wire
        # contract matches the previous explicit-zero behavior.
        return math.ceil(self.total / self.per_page) if self.total else 0


class PaginatedListResponse(APIModel, Generic[T]):
    data: list[T]
    meta: PaginationMeta


_ERROR_RESPONSE_DESCRIPTIONS = {
    400: "Bad request.",
    401: "Missing or invalid bearer token.",
    403: "Authenticated but not authorized for this operation.",
    404: "Resource was not found or has been soft-deleted.",
    409: "Conflict, optimistic-lock mismatch, duplicate request, or invalid transition.",
    413: "Request body exceeds the allowed size.",
    415: "Unsupported media type.",
    422: "Validation error.",
    429: "Rate limit exceeded.",
    500: "Unexpected server condition.",
    503: "Transient backend failure.",
}


def error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    return {
        status_code: {
            "model": ErrorResponse,
            "description": _ERROR_RESPONSE_DESCRIPTIONS.get(status_code, "Error."),
        }
        for status_code in status_codes
    }


def like_pattern(query: str) -> str:
    """Escape SQL LIKE wildcards in user-supplied search terms.

    `%` and `_` are LIKE metacharacters; passing a raw user query like ``%``
    would otherwise match every row. Pair this with ``column.ilike(pattern,
    escape="\\\\")`` so the backslash escapes are honored by the database.
    """
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
