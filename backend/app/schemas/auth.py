from __future__ import annotations

from pydantic import EmailStr, Field, field_validator

from app.core.security import WeakPasswordError, validate_password_policy
from app.schemas.common import APIModel


class RegisterRequest(APIModel):
    """Public self-registration payload. Role is always assigned server-side (holder).

    Decision A2 — see docs/system-design/12-api-design.md §1.1: any incoming `role`
    field is silently dropped (extra='ignore' on APIModel); the endpoint pins the
    new user to UserRole.HOLDER regardless of client input.
    """

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=100)
    department: str = Field(min_length=1, max_length=100)

    @field_validator("password")
    @classmethod
    def _enforce_password_policy(cls, value: str) -> str:
        try:
            validate_password_policy(value)
        except WeakPasswordError as exc:
            raise ValueError(str(exc)) from exc
        return value
