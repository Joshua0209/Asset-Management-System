from __future__ import annotations

from datetime import datetime

from app.models.user import UserRole
from app.schemas.common import APIModel


class UserRead(APIModel):
    id: str
    email: str
    name: str
    role: UserRole
    department: str
    version: int
    created_at: datetime
    updated_at: datetime
