from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.asset import Asset, AssetStatus
from app.models.asset_action_history import AssetAction, AssetActionHistory
from app.models.user import User

# Asset registration (FSM T1) is intentionally NOT in AssetAction. The asset
# row's own ``created_at`` is its audit signal; ``asset_action_histories`` only
# records transitions on existing assets, per docs/system-design/11-asset-fsm.md
# and the design doc's "one row per FSM transition" wording.


def record_asset_action(
    db: Session,
    *,
    asset: Asset,
    actor: User,
    action: AssetAction,
    from_status: AssetStatus,
    to_status: AssetStatus,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Add a history row to the session as part of the caller's transaction.

    Intentionally does NOT call ``db.commit()`` — the caller's existing
    commit (e.g., the FSM endpoint or ``_commit_repair_change``) flushes
    and persists the row atomically with the state change. This is what
    makes the audit-trail invariant ("no transition without log") hold.

    Pre-validates that ``metadata`` is JSON-serializable so a non-encodable
    value surfaces as a clear ``TypeError`` here, not a generic flush error
    later that would land in the unhandled-exception envelope handler.
    """
    if not db.in_transaction():
        # Without an open transaction, the row would be auto-committed alone
        # — defeating the atomicity invariant. This catches "forgot to wrap
        # the FSM mutation in a transaction" regressions in tests.
        raise RuntimeError(
            "record_asset_action requires an open transaction so the audit row "
            "commits atomically with the FSM state change."
        )
    if metadata is not None:
        try:
            json.dumps(metadata)
        except (TypeError, ValueError) as exc:
            raise TypeError(
                f"audit_log metadata is not JSON-serializable for "
                f"action={action.value}: {exc}"
            ) from exc
    history = AssetActionHistory(
        asset_id=asset.id,
        actor_id=actor.id,
        action=action,
        from_status=from_status,
        to_status=to_status,
        event_metadata=metadata,
    )
    db.add(history)
