"""ORM models.

Importing this package eagerly registers every model module with
SQLAlchemy's declarative registry, so string relationship references
(e.g. ``order_by="AssetActionHistory.created_at.desc()"`` on
``Asset.action_histories``) resolve no matter which submodule the
caller imports first. Without this, scripts that touch only a subset
of models — most notably ``scripts/seed_demo_data.py`` — hit
``InvalidRequestError`` during ``configure_mappers()`` (see issue #47).
"""

from app.models import (  # noqa: F401  (side-effect imports)
    asset,
    asset_action_history,
    repair_image,
    repair_request,
    user,
)
