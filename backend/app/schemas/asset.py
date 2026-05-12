from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field, model_validator

from app.models.asset import AssetStatus
from app.models.asset_action_history import AssetAction
from app.schemas.common import APIModel, UUIDString


def _today_utc() -> date:
    """Return today's date in UTC to match the project's ISO-8601-UTC convention."""
    return datetime.now(UTC).date()


AssetCategory = Literal[
    "phone",
    "computer",
    "tablet",
    "monitor",
    "printer",
    "network_equipment",
    "other",
]


class AssetCreate(APIModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=120)
    specs: str | None = Field(default=None, max_length=500)
    category: AssetCategory
    supplier: str = Field(min_length=1, max_length=120)
    purchase_date: date
    purchase_amount: Decimal = Field(gt=0, max_digits=15, decimal_places=2)
    location: str | None = Field(default=None, max_length=120)
    department: str | None = Field(default=None, max_length=100)
    activation_date: date | None = None
    warranty_expiry: date | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> AssetCreate:
        if self.purchase_date > _today_utc():
            raise ValueError("purchase_date must not be in the future")
        if self.warranty_expiry is not None and self.warranty_expiry <= self.purchase_date:
            raise ValueError("warranty_expiry must be after purchase_date")
        return self


class AssetUpdate(APIModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    model: str | None = Field(default=None, min_length=1, max_length=120)
    specs: str | None = Field(default=None, max_length=500)
    category: AssetCategory | None = None
    supplier: str | None = Field(default=None, min_length=1, max_length=120)
    purchase_date: date | None = None
    purchase_amount: Decimal | None = Field(default=None, gt=0, max_digits=15, decimal_places=2)
    location: str | None = Field(default=None, max_length=120)
    department: str | None = Field(default=None, max_length=100)
    activation_date: date | None = None
    warranty_expiry: date | None = None
    version: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_consistency(self) -> AssetUpdate:
        non_nullable_fields = {
            "name",
            "model",
            "category",
            "supplier",
            "purchase_date",
            "purchase_amount",
        }
        for field_name in non_nullable_fields:
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        if self.purchase_date is not None and self.purchase_date > _today_utc():
            raise ValueError("purchase_date must not be in the future")
        if (
            self.purchase_date is not None
            and self.warranty_expiry is not None
            and self.warranty_expiry <= self.purchase_date
        ):
            raise ValueError("warranty_expiry must be after purchase_date")
        return self


class AssetAssignRequest(APIModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    responsible_person_id: UUIDString
    assignment_date: date
    version: int = Field(ge=1)

    @model_validator(mode="after")
    def _validate_assignment_date(self) -> AssetAssignRequest:
        if self.assignment_date > _today_utc():
            raise ValueError("assignment_date must not be in the future")
        return self


class AssetUnassignRequest(APIModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    reason: str = Field(min_length=1, max_length=500)
    unassignment_date: date
    version: int = Field(ge=1)

    @model_validator(mode="after")
    def _validate_unassignment_date(self) -> AssetUnassignRequest:
        # Cross-field check against the asset's stored assignment_date is the
        # endpoint's job (this validator only knows the payload). Future-date
        # rejection lives here so it surfaces as a regular schema error.
        if self.unassignment_date > _today_utc():
            raise ValueError("unassignment_date must not be in the future")
        return self


class AssetDisposeRequest(APIModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    disposal_reason: str = Field(min_length=1, max_length=500)
    version: int = Field(ge=1)


class AssetPersonRead(APIModel):
    id: str
    name: str
    email: str


class AssetRead(APIModel):
    id: str
    asset_code: str
    name: str
    model: str
    specs: str | None
    category: str
    supplier: str
    purchase_date: date
    purchase_amount: Decimal
    location: str
    department: str
    activation_date: date | None
    warranty_expiry: date | None
    assignment_date: date | None
    unassignment_date: date | None
    status: AssetStatus
    responsible_person_id: str | None
    responsible_person: AssetPersonRead | None
    disposal_reason: str | None
    version: int
    created_at: datetime | None
    updated_at: datetime | None


class ActorRef(APIModel):
    id: str
    name: str


# Per-action metadata variants. Each carries a Literal discriminator so the
# `metadata` field on AssetActionHistoryRead becomes a Pydantic v2 tagged
# union: OpenAPI emits `oneOf` + `discriminator: action`, which TypeScript
# generators turn into a real discriminated union (`switch (event.action)`
# is exhaustive, no `as any` casts in the timeline UI).
#
# `extra="forbid"` is intentional — a typo in a future writer (or a renamed
# field that didn't get propagated here) raises ValidationError at the schema
# boundary instead of silently dropping data. The writers don't change; they
# already pass dicts matching these shapes. The redundant `action` key in
# each variant is injected from the parent in `_inject_action_into_metadata`
# below, so writer call sites stay untouched.


class _MetadataVariant(APIModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class AssignMetadata(_MetadataVariant):
    action: Literal[AssetAction.ASSIGN] = AssetAction.ASSIGN
    responsible_person_id: UUIDString
    responsible_person_name: str


class UnassignMetadata(_MetadataVariant):
    action: Literal[AssetAction.UNASSIGN] = AssetAction.UNASSIGN
    reason: str
    # Defensive `| None`: FSM precondition (status=IN_USE) implies a
    # responsible_person is set, but the writer at endpoints/assets.py
    # snapshots `asset.responsible_person_id` directly — if that ever
    # desyncs from status, we'd write None rather than crash.
    previous_responsible_person_id: UUIDString | None = None


class DisposeMetadata(_MetadataVariant):
    action: Literal[AssetAction.DISPOSE] = AssetAction.DISPOSE
    disposal_reason: str


class SubmitRepairMetadata(_MetadataVariant):
    action: Literal[AssetAction.SUBMIT_REPAIR] = AssetAction.SUBMIT_REPAIR
    repair_request_id: UUIDString
    fault_description: str


class ApproveRepairMetadata(_MetadataVariant):
    action: Literal[AssetAction.APPROVE_REPAIR] = AssetAction.APPROVE_REPAIR
    repair_request_id: UUIDString


class RejectRepairMetadata(_MetadataVariant):
    action: Literal[AssetAction.REJECT_REPAIR] = AssetAction.REJECT_REPAIR
    repair_request_id: UUIDString
    rejection_reason: str


class CompleteRepairMetadata(_MetadataVariant):
    action: Literal[AssetAction.COMPLETE_REPAIR] = AssetAction.COMPLETE_REPAIR
    repair_request_id: UUIDString
    # String-encoded Decimal so the JSON column encodes deterministically
    # without MySQL JSON precision drift. See the writer at
    # backend/app/api/v1/endpoints/repair_requests.py inside
    # complete_repair_request for the matching `str(payload.repair_cost)`.
    repair_cost: str
    repair_vendor: str


AssetActionHistoryMetadata = Annotated[
    AssignMetadata
    | UnassignMetadata
    | DisposeMetadata
    | SubmitRepairMetadata
    | ApproveRepairMetadata
    | RejectRepairMetadata
    | CompleteRepairMetadata,
    Field(discriminator="action"),
]


class AssetActionHistoryRead(APIModel):
    # `from_attributes=True` (inherited via APIModel) populates by attr name,
    # so the SQLAlchemy attribute `event_metadata` maps to the wire field
    # `metadata` here. The serialization alias is what the JSON consumer sees.
    # `populate_by_name=True` is load-bearing alongside the alias: it keeps
    # both the attr name (`event_metadata`) and the alias (`metadata`)
    # accepted on input, so neither ORM attribute access nor a hand-built
    # dict breaks. (StrEnum on action/from_status/to_status renders as the
    # enum value on the wire, but constrains OpenAPI to a known set.)
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    action: AssetAction
    from_status: AssetStatus
    to_status: AssetStatus
    actor: ActorRef | None
    metadata: AssetActionHistoryMetadata | None = Field(
        default=None,
        validation_alias="event_metadata",
        serialization_alias="metadata",
    )
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _inject_action_into_metadata(cls, data: Any) -> Any:
        # The DB JSON column doesn't store `action` inside the metadata blob
        # — writers pass shape-only dicts. Copy the sibling `action` onto a
        # shallow clone of the metadata dict so the discriminated union has
        # its discriminator. Handles both dict input (tests/API bodies) and
        # ORM input (from_attributes path through model_validate).
        if data is None:
            return data
        if isinstance(data, dict):
            action = data.get("action")
            if action is None:
                return data
            for key in ("metadata", "event_metadata"):
                md = data.get(key)
                if isinstance(md, dict) and "action" not in md:
                    return {**data, key: {**md, "action": action}}
            return data
        # ORM path: rebuild as a dict so we can mutate the metadata blob
        # without touching the SQLAlchemy row. Nested ActorRef still
        # resolves through `from_attributes` because that flag is inherited
        # via APIModel — Pydantic re-validates the User object recursively.
        action = getattr(data, "action", None)
        metadata = getattr(data, "event_metadata", None)
        if action is None or not isinstance(metadata, dict) or "action" in metadata:
            return data
        return {
            "id": getattr(data, "id", None),
            "action": action,
            "from_status": getattr(data, "from_status", None),
            "to_status": getattr(data, "to_status", None),
            "actor": getattr(data, "actor", None),
            "event_metadata": {**metadata, "action": action},
            "created_at": getattr(data, "created_at", None),
        }
