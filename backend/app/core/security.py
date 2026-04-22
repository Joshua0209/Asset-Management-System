"""Password hashing and JWT access-token primitives.

Pure functions — no FastAPI imports here so this module is reusable from the
seed script, background jobs, and tests without pulling a web framework in.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import get_settings
from app.models.user import UserRole


class InvalidTokenError(Exception):
    """Raised when an access token is missing, expired, tampered, or signed with a foreign key."""


@dataclass(frozen=True)
class TokenPayload:
    sub: str
    role: UserRole
    exp: datetime


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Malformed stored hash — treat as failed verification, not a crash.
        return False


def create_access_token(
    subject: str,
    role: UserRole,
    expires_minutes: int | None = None,
) -> tuple[str, datetime]:
    settings = get_settings()
    minutes = (
        settings.jwt_access_token_expires_minutes
        if expires_minutes is None
        else expires_minutes
    )
    expires_at = datetime.now(UTC) + timedelta(minutes=minutes)
    token = jwt.encode(
        {"sub": subject, "role": role.value, "exp": expires_at},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return token, expires_at


def decode_access_token(token: str) -> TokenPayload:
    settings = get_settings()
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc

    try:
        return TokenPayload(
            sub=str(claims["sub"]),
            role=UserRole(claims["role"]),
            exp=datetime.fromtimestamp(int(claims["exp"]), tz=UTC),
        )
    except (KeyError, ValueError) as exc:
        raise InvalidTokenError(f"Malformed token claims: {exc}") from exc
