from __future__ import annotations

import logging
from datetime import UTC, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, desc, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.functions import Function

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


@router.get(
    "/manager",
    summary="Manager dashboard summary",
)
def get_manager_dashboard(
    db: DbSession,
    _current: ManagerUser,
) -> DataResponse[ManagerDashboard]:
    try:
        # `total_assets` excludes DISPOSED so it matches the sum of the
        # active-status buckets. Disposed rows stay in the table for
        # auditability but are not part of the "currently managed" view.
        non_disposed = Asset.status != AssetStatus.DISPOSED

        # One round-trip for every asset KPI. MySQL 8 doesn't support
        # FILTER on aggregates, so use SUM(CASE WHEN ...) which is portable
        # and lets the planner do all work in a single table pass.
        def _bucket(predicate: ColumnElement[bool]) -> Function[int]:
            return func.coalesce(func.sum(case((predicate, 1), else_=0)), 0)

        asset_row = db.execute(
            select(
                _bucket(non_disposed).label("total"),
                _bucket(Asset.status == AssetStatus.IN_STOCK).label("in_stock"),
                _bucket(Asset.status == AssetStatus.IN_USE).label("in_use"),
                _bucket(Asset.status == AssetStatus.PENDING_REPAIR).label(
                    "pending_repair"
                ),
                _bucket(Asset.status == AssetStatus.UNDER_REPAIR).label(
                    "under_repair"
                ),
            ).select_from(Asset)
        ).one()

        # Order by count desc then category asc — deterministic for equal
        # buckets so tests and the UI render the same sequence.
        category_rows = db.execute(
            # Label is `category_count` (not `count`) to avoid shadowing
            # SQLAlchemy `Row.count()` — `row.count` would resolve to the
            # bound method instead of the aggregate value under mypy strict.
            select(Asset.category, func.count().label("category_count"))
            .where(non_disposed)
            .group_by(Asset.category)
            .order_by(desc("category_count"), Asset.category.asc())
        ).all()
        asset_categories = [
            AssetCategoryCount(category=row.category, count=row.category_count)
            for row in category_rows
        ]

        # All timestamps are stored UTC; converting to local TZ here would
        # couple the API contract to the server's clock config.
        today_start = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)
        tomorrow_start = today_start + timedelta(days=1)

        # Single-pass repair-summary aggregation. The same `pending_review`
        # value also appears under `kpis.pending_repair_requests`; both are
        # derived from this SUM(CASE ...) row so they cannot drift apart.
        repair_row = db.execute(
            select(
                _bucket(
                    (RepairRequest.created_at >= today_start)
                    & (RepairRequest.created_at < tomorrow_start)
                ).label("created_today"),
                _bucket(
                    RepairRequest.status == RepairRequestStatus.PENDING_REVIEW
                ).label("pending_review"),
                _bucket(
                    RepairRequest.status == RepairRequestStatus.UNDER_REPAIR
                ).label("under_repair"),
                _bucket(
                    (RepairRequest.status == RepairRequestStatus.COMPLETED)
                    & RepairRequest.completed_at.is_not(None)
                    & (RepairRequest.completed_at >= today_start)
                    & (RepairRequest.completed_at < tomorrow_start)
                ).label("completed_today"),
            ).select_from(RepairRequest)
        ).one()

        repair_summary = RepairSummary(
            created_today=int(repair_row.created_today),
            pending_review=int(repair_row.pending_review),
            under_repair=int(repair_row.under_repair),
            completed_today=int(repair_row.completed_today),
        )

        kpis = DashboardKpis(
            total_assets=int(asset_row.total),
            in_stock_assets=int(asset_row.in_stock),
            in_use_assets=int(asset_row.in_use),
            pending_repair_assets=int(asset_row.pending_repair),
            under_repair_assets=int(asset_row.under_repair),
            # Sourced from the same row as repair_summary.pending_review so
            # the KPI and the summary card cannot disagree.
            pending_repair_requests=repair_summary.pending_review,
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
                # MySQL DATETIME comes back naive — attach UTC so the
                # serialised JSON carries an explicit offset.
                created_at=row.created_at.replace(tzinfo=UTC)
                if row.created_at.tzinfo is None
                else row.created_at,
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
        # Structured detail picks a granular code within 503; the
        # global handler in app/main.py rewraps this into the project's
        # {"error": {"code", "message"}} envelope.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "dashboard_unavailable",
                "message": "Unable to load dashboard. Please try again later.",
            },
        ) from exc
