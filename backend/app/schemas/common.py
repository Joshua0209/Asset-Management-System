from __future__ import annotations

from typing import Annotated, Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")

UUID_PATTERN = (
    r"^[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}$"
)
UUIDString = Annotated[str, Field(pattern=UUID_PATTERN, json_schema_extra={"format": "uuid"})]


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


_ERROR_RESPONSE_DESCRIPTIONS = {
    400: "Malformed JSON or bad request.",
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
