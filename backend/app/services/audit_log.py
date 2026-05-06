from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.asset import Asset, AssetStatus
from app.models.asset_action_history import AssetAction, AssetActionHistory
from app.models.user import User


def record_asset_action(
    db: Session,
    *,
    asset: Asset,
    actor: User,
    action: AssetAction,
    from_status: AssetStatus,
    to_status: AssetStatus,
    metadata: dict[str, Any] | None = None,
) -> AssetActionHistory:
    """Add a history row to the session as part of the caller's transaction.

    Intentionally does NOT call ``db.commit()`` — the caller's existing
    commit (e.g., the FSM endpoint or ``_commit_repair_change``) flushes
    and persists the row atomically with the state change. This is what
    makes the audit-trail invariant ("no transition without log") hold.
    """
    history = AssetActionHistory(
        asset_id=asset.id,
        actor_id=actor.id,
        action=action.value,
        from_status=from_status.value,
        to_status=to_status.value,
        event_metadata=metadata,
    )
    db.add(history)
    return history
