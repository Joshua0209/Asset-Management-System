from __future__ import annotations

from app.models.user import UserRole
from app.schemas.common import APIModel, UtcDatetime


class UserRead(APIModel):
    id: str
    email: str
    name: str
    role: UserRole
    department: str
    location: str
    version: int
    created_at: UtcDatetime
    updated_at: UtcDatetime
