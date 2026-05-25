from __future__ import annotations

from pydantic import AwareDatetime, Field

from app.models.repair_request import RepairRequestStatus
from app.schemas.common import APIModel, UUIDString


class DashboardKpis(APIModel):
    total_assets: int = Field(ge=0)
    in_stock_assets: int = Field(ge=0)
    in_use_assets: int = Field(ge=0)
    pending_repair_assets: int = Field(ge=0)
    under_repair_assets: int = Field(ge=0)
    pending_repair_requests: int = Field(ge=0)


class AssetCategoryCount(APIModel):
    category: str
    count: int = Field(ge=0)


class RepairSummary(APIModel):
    created_today: int = Field(ge=0)
    pending_review: int = Field(ge=0)
    under_repair: int = Field(ge=0)
    completed_today: int = Field(ge=0)


class RecentPendingRepair(APIModel):
    id: UUIDString
    repair_id: str
    asset_id: UUIDString
    asset_name: str
    requester_name: str
    status: RepairRequestStatus
    # Aware datetime — MySQL stores naive UTC; the endpoint attaches
    # tzinfo=UTC on read so clients never have to guess the offset.
    created_at: AwareDatetime


class ManagerDashboard(APIModel):
    kpis: DashboardKpis
    asset_categories: list[AssetCategoryCount]
    repair_summary: RepairSummary
    recent_pending_repairs: list[RecentPendingRepair]
