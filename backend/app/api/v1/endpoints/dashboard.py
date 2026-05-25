from __future__ import annotations

import logging
from datetime import UTC, datetime, time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import ManagerUser
from app.db.session import get_db
from app.models.asset import Asset, AssetStatus
from app.models.repair_request import RepairRequest, RepairRequestStatus
from app.models.user import User
from app.schemas.common import DataResponse, error_responses
from app.schemas.dashboard import (
    AssetCategoryCount,
    DashboardKpis,
    ManagerDashboard,
    RecentPendingRepair,
    RepairSummary,
)

logger = logging.getLogger(__name__)
router = APIRouter(
    responses=error_responses(
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
        status.HTTP_503_SERVICE_UNAVAILABLE,
    )
)

DbSession = Annotated[Session, Depends(get_db)]

_RECENT_PENDING_LIMIT = 3


@router.get("/manager", summary="Manager dashboard summary")
def get_manager_dashboard(
    db: DbSession,
    _current: ManagerUser,
) -> DataResponse[ManagerDashboard]:
    try:
        # `total_assets` excludes DISPOSED so it matches the sum of the
        # active-status buckets. Disposed rows stay in the table for
        # auditability but are not part of the "currently managed" view.
        non_disposed = Asset.status != AssetStatus.DISPOSED

        total_assets = db.scalar(
            select(func.count()).select_from(Asset).where(non_disposed)
        ) or 0
        in_use_assets = db.scalar(
            select(func.count())
            .select_from(Asset)
            .where(Asset.status == AssetStatus.IN_USE)
        ) or 0
        under_repair_assets = db.scalar(
            select(func.count())
            .select_from(Asset)
            .where(Asset.status == AssetStatus.UNDER_REPAIR)
        ) or 0
        pending_repair_requests = db.scalar(
            select(func.count())
            .select_from(RepairRequest)
            .where(RepairRequest.status == RepairRequestStatus.PENDING_REVIEW)
        ) or 0

        kpis = DashboardKpis(
            total_assets=total_assets,
            in_use_assets=in_use_assets,
            under_repair_assets=under_repair_assets,
            pending_repair_requests=pending_repair_requests,
        )

        # Order by count desc then category asc — deterministic for equal
        # buckets so tests and the UI render the same sequence.
        category_rows = db.execute(
            select(Asset.category, func.count().label("count"))
            .where(non_disposed)
            .group_by(Asset.category)
            .order_by(desc("count"), Asset.category.asc())
        ).all()
        asset_categories = [
            AssetCategoryCount(category=row.category, count=row.count)
            for row in category_rows
        ]

        # All timestamps are stored UTC; converting to local TZ here would
        # couple the API contract to the server's clock config.
        today_start = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)

        created_today = db.scalar(
            select(func.count())
            .select_from(RepairRequest)
            .where(RepairRequest.created_at >= today_start)
        ) or 0
        summary_pending = db.scalar(
            select(func.count())
            .select_from(RepairRequest)
            .where(RepairRequest.status == RepairRequestStatus.PENDING_REVIEW)
        ) or 0
        summary_under_repair = db.scalar(
            select(func.count())
            .select_from(RepairRequest)
            .where(RepairRequest.status == RepairRequestStatus.UNDER_REPAIR)
        ) or 0
        completed_today = db.scalar(
            select(func.count())
            .select_from(RepairRequest)
            .where(
                RepairRequest.status == RepairRequestStatus.COMPLETED,
                RepairRequest.completed_at.is_not(None),
                RepairRequest.completed_at >= today_start,
            )
        ) or 0

        repair_summary = RepairSummary(
            created_today=created_today,
            pending_review=summary_pending,
            under_repair=summary_under_repair,
            completed_today=completed_today,
        )

        # Explicit join on just the columns we need avoids the N+1 lazy
        # loads that joinedload would still trigger for nested relations.
        recent_rows = db.execute(
            select(
                RepairRequest.id,
                RepairRequest.repair_id,
                RepairRequest.asset_id,
                RepairRequest.status,
                RepairRequest.created_at,
                Asset.name.label("asset_name"),
                User.name.label("requester_name"),
            )
            .join(Asset, Asset.id == RepairRequest.asset_id)
            .join(User, User.id == RepairRequest.requester_id)
            .where(RepairRequest.status == RepairRequestStatus.PENDING_REVIEW)
            .order_by(RepairRequest.created_at.desc())
            .limit(_RECENT_PENDING_LIMIT)
        ).all()
        recent_pending_repairs = [
            RecentPendingRepair(
                id=row.id,
                repair_id=row.repair_id,
                asset_id=row.asset_id,
                asset_name=row.asset_name,
                requester_name=row.requester_name,
                status=row.status,
                created_at=row.created_at,
            )
            for row in recent_rows
        ]

        return DataResponse(
            data=ManagerDashboard(
                kpis=kpis,
                asset_categories=asset_categories,
                repair_summary=repair_summary,
                recent_pending_repairs=recent_pending_repairs,
            )
        )
    except SQLAlchemyError as exc:
        logger.exception("Failed to build manager dashboard")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to load dashboard. Please try again later.",
        ) from exc
