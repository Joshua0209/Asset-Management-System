from __future__ import annotations

import logging
import os
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.asset import Asset, AssetStatus
from app.models.asset_action_history import AssetAction, AssetActionHistory
from app.models.repair_image import RepairImage
from app.models.repair_request import RepairRequest, RepairRequestStatus
from app.models.user import User, UserRole

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEPARTMENTS = ["IT", "HR", "Finance", "Operations"]
LOCATIONS = ["Taipei HQ", "Hsinchu Office", "Taichung Branch"]
SUPPLIERS = ["Apple", "Dell", "Lenovo", "ASUS", "Samsung"]
# Category strings MUST match ``AssetCategory`` in ``app/schemas/asset.py``
# (the API Literal). The DB column is plain ``String(100)`` so non-canonical
# values would insert without error but then fail every API write and vanish
# from the UI's category filter. Pinned by
# ``test_seed_categories_match_asset_category_literal``.
CATEGORIES = ["computer", "phone", "tablet", "monitor", "other"]
ASSET_NAMES = {
    "computer": "Business Laptop",
    "phone": "Company Phone",
    "tablet": "Field Tablet",
    "monitor": "Office Monitor",
    "other": "Docking Station",
}
MODELS = {
    "computer": ["Dell Latitude 7440", "MacBook Pro 14", "ThinkPad T14"],
    "phone": ["iPhone 15", "Galaxy S24", "Pixel 9"],
    "tablet": ["iPad Air", "Galaxy Tab S9", "Surface Go 4"],
    "monitor": ["Dell U2723QE", "LG 27UP850", "ASUS ProArt 27"],
    "other": ["Dell WD22TB4", "Anker Hub 565", "Lenovo Dock Gen 2"],
}
FAULT_DESCRIPTIONS = [
    "Screen flickers intermittently during work.",
    "Battery drains unusually fast after charging.",
    "Device overheats when running normal office apps.",
    "Wi-Fi disconnects several times a day.",
    "Keyboard keys sometimes stop responding.",
]
DEMO_JPEG_BYTES = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00"
    b"\xff\xdb\x00C\x00\x03\x02\x02\x02\x02\x02\x03\x02\x02\x02\x03\x03"
    b"\x03\x03\x04\x06\x04\x04\x04\x04\x04\x08\x06\x06\x05\x06\t\x08\n"
    b"\n\t\x08\t\t\n\x0c\x0f\r\n\x0b\x0e\x0b\t\t\r\x11\r\x0e\x0f\x10"
    b"\x10\x11\x10\n\x0c\x12\x13\x12\x10\x13\x0f\x10\x10\x10\xff\xc0"
    b"\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00"
    b"\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10"
    b"\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01}\x01"
    b'\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07"q\x142\x81\x91\xa1'
    b"\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17\x18\x19\x1a%&'()"
    b"*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x83\x84\x85\x86\x87\x88"
    b"\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6"
    b"\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4"
    b"\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1"
    b"\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5\xf6\xf7"
    b"\xf8\xf9\xfa\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xfd\xfc\xf1\xff"
    b"\xd9"
)


def build_bootstrap_manager() -> User:
    """The constant-identity manager so the system is usable right after seeding.

    Credentials come from BOOTSTRAP_MANAGER_* env vars (see .env.example).
    Change these before exposing the system outside the team.
    """
    settings = get_settings()
    return User(
        email=settings.bootstrap_manager_email,
        password_hash=hash_password(settings.bootstrap_manager_password),
        name=settings.bootstrap_manager_name,
        role=UserRole.MANAGER,
        department=settings.bootstrap_manager_department,
    )


def build_users() -> list[User]:
    bootstrap = build_bootstrap_manager()
    users: list[User] = [bootstrap]
    # The bootstrap email wins on conflict so seeding stays idempotent regardless
    # of how BOOTSTRAP_MANAGER_EMAIL is overridden — without this guard, setting
    # it to e.g. "manager1@example.com" raises a unique-constraint error on flush.
    seen_emails = {bootstrap.email}

    for index in range(2):
        email = f"manager{index + 1}@example.com"
        if email in seen_emails:
            continue
        users.append(
            User(
                email=email,
                password_hash=hash_password("Password123"),
                name=f"Manager {index + 1}",
                role=UserRole.MANAGER,
                department=DEPARTMENTS[index],
            )
        )
        seen_emails.add(email)
    for index in range(2):
        email = f"holder{index + 1}@example.com"
        if email in seen_emails:
            continue
        users.append(
            User(
                email=email,
                password_hash=hash_password("Password123"),
                name=f"Holder {index + 1}",
                role=UserRole.HOLDER,
                department=DEPARTMENTS[index + 2],
            )
        )
        seen_emails.add(email)
    return users


def build_assets(holders: list[User]) -> list[Asset]:
    assets: list[Asset] = []
    today = date.today()
    for index in range(50):
        category = CATEGORIES[index % len(CATEGORIES)]
        holder = holders[index % len(holders)] if index % 3 != 0 else None
        status = AssetStatus.IN_USE if holder else AssetStatus.IN_STOCK
        purchase_date = today - timedelta(days=40 + index * 7)
        assets.append(
            Asset(
                asset_code=f"AST-{today.year}-{index + 1:05d}",
                name=ASSET_NAMES[category],
                model=MODELS[category][index % len(MODELS[category])],
                specs=f"{category} demo configuration #{index + 1}",
                category=category,
                supplier=SUPPLIERS[index % len(SUPPLIERS)],
                purchase_date=purchase_date,
                purchase_amount=Decimal("1500.00") + Decimal(index * 25),
                location=LOCATIONS[index % len(LOCATIONS)],
                department=holder.department if holder else DEPARTMENTS[index % len(DEPARTMENTS)],
                activation_date=purchase_date + timedelta(days=3),
                warranty_expiry=purchase_date + timedelta(days=365 * 2),
                status=status,
                responsible_person_id=holder.id if holder else None,
                assignment_date=(purchase_date + timedelta(days=10) if holder else None),
            )
        )
    # Two DISPOSED assets so the dispose branch, ``disposal_reason``, and
    # ``unassignment_date`` are all exercised. Per the dispose endpoint
    # (``app/api/v1/endpoints/assets.py``), the FSM requires IN_STOCK with no
    # responsible_person before transitioning to DISPOSED, so we leave both
    # cleared here and write a matching DISPOSE audit row in
    # ``build_action_histories``.
    for offset in range(2):
        index = 50 + offset
        category = CATEGORIES[index % len(CATEGORIES)]
        purchase_date = today - timedelta(days=400 + index * 7)
        assets.append(
            Asset(
                asset_code=f"AST-{today.year}-{index + 1:05d}",
                name=ASSET_NAMES[category],
                model=MODELS[category][index % len(MODELS[category])],
                specs=f"{category} retired configuration #{offset + 1}",
                category=category,
                supplier=SUPPLIERS[index % len(SUPPLIERS)],
                purchase_date=purchase_date,
                purchase_amount=Decimal("1500.00") + Decimal(index * 25),
                location=LOCATIONS[index % len(LOCATIONS)],
                department=DEPARTMENTS[index % len(DEPARTMENTS)],
                activation_date=purchase_date + timedelta(days=3),
                warranty_expiry=purchase_date + timedelta(days=365 * 2),
                status=AssetStatus.DISPOSED,
                responsible_person_id=None,
                assignment_date=None,
                unassignment_date=today - timedelta(days=30),
                disposal_reason="End-of-life replacement after warranty expiry.",
            )
        )
    return assets


def build_repair_requests(
    assets: list[Asset],
    holders: list[User],
    managers: list[User],
) -> list[RepairRequest]:
    requests: list[RepairRequest] = []
    holders_by_id = {holder.id: holder for holder in holders}
    in_use_assets = [item for item in assets if item.status == AssetStatus.IN_USE][:10]
    for index, asset in enumerate(in_use_assets):
        assert asset.responsible_person_id is not None, (
            f"IN_USE asset {asset.asset_code} has no responsible_person_id; "
            "seed data is inconsistent."
        )
        manager = managers[index % len(managers)]
        holder = holders_by_id[asset.responsible_person_id]
        status_cycle = [
            RepairRequestStatus.PENDING_REVIEW,
            RepairRequestStatus.UNDER_REPAIR,
            RepairRequestStatus.COMPLETED,
            RepairRequestStatus.REJECTED,
        ]
        status = status_cycle[index % len(status_cycle)]
        repair_request = RepairRequest(
            asset_id=asset.id,
            # Sequential within this seed run; _next_repair_id will resume
            # from the highest existing repair_id when the endpoint is called post-seed.
            repair_id=f"REP-{date.today().year}-{index + 1:05d}",
            requester_id=holder.id,
            reviewer_id=manager.id if status != RepairRequestStatus.PENDING_REVIEW else None,
            status=status,
            fault_description=FAULT_DESCRIPTIONS[index % len(FAULT_DESCRIPTIONS)],
        )
        if status in {RepairRequestStatus.UNDER_REPAIR, RepairRequestStatus.COMPLETED}:
            repair_request.repair_date = date.today() - timedelta(days=index + 2)
            repair_request.fault_content = f"Verified issue for {asset.asset_code}"
            repair_request.repair_plan = "Replace worn component and validate stability."
            repair_request.repair_cost = Decimal("250.00") + Decimal(index * 10)
            repair_request.repair_vendor = "FixIt Services"
        if status == RepairRequestStatus.REJECTED:
            repair_request.rejection_reason = "Issue could not be reproduced during review."
        if status == RepairRequestStatus.COMPLETED:
            repair_request.completed_at = datetime.now(UTC)
        requests.append(repair_request)

        if status == RepairRequestStatus.PENDING_REVIEW:
            asset.status = AssetStatus.PENDING_REPAIR
        elif status == RepairRequestStatus.UNDER_REPAIR:
            asset.status = AssetStatus.UNDER_REPAIR
        else:
            asset.status = AssetStatus.IN_USE
    return requests


def build_images(repair_requests: list[RepairRequest]) -> list[RepairImage]:
    images: list[RepairImage] = []
    upload_root = Path(get_settings().repair_upload_dir)
    for request in repair_requests[:6]:
        image_id = str(uuid.uuid4())
        storage_key = f"{request.id}/{image_id}.jpg"
        target = upload_root / storage_key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(DEMO_JPEG_BYTES)
        images.append(
            RepairImage(
                id=image_id,
                repair_request_id=request.id,
                image_url=storage_key,
            )
        )
    return images


def build_action_histories(
    assets: list[Asset],
    repair_requests: list[RepairRequest],
    holders: list[User],
    managers: list[User],
) -> list[AssetActionHistory]:
    """Backfill an FSM-consistent audit trail for each seeded asset.

    Asset registration (FSM T1, → IN_STOCK) is intentionally NOT recorded; the
    asset row's own ``created_at`` is its audit signal per
    ``docs/system-design/11-asset-fsm.md``. Every other terminal state the seed
    manufactures (IN_USE, PENDING_REPAIR, UNDER_REPAIR, DISPOSED) gets the
    transitions that would have produced it.
    """
    histories: list[AssetActionHistory] = []
    base = datetime.now(UTC)

    holders_by_id = {holder.id: holder for holder in holders}
    repair_requests_by_asset = {rr.asset_id: rr for rr in repair_requests}
    # Bootstrap manager is first in ``users`` so this is a stable default actor
    # for transitions whose original manager identity is not recoverable
    # (ASSIGN, DISPOSE — repair_requests own ``reviewer_id`` and are used
    # directly below).
    default_manager = managers[0]
    managers_by_id = {m.id: m for m in managers}

    for asset in assets:
        if asset.status is AssetStatus.IN_STOCK:
            continue
        if asset.status is AssetStatus.DISPOSED:
            histories.append(
                AssetActionHistory(
                    asset_id=asset.id,
                    actor_id=default_manager.id,
                    action=AssetAction.DISPOSE,
                    from_status=AssetStatus.IN_STOCK,
                    to_status=AssetStatus.DISPOSED,
                    event_metadata={"disposal_reason": asset.disposal_reason},
                    created_at=base - timedelta(days=10),
                )
            )
            continue

        # IN_USE-derived statuses (IN_USE, PENDING_REPAIR, UNDER_REPAIR) imply
        # an ASSIGN happened — and ``build_assets`` always sets
        # responsible_person_id on those, so the lookup is safe.
        assert asset.responsible_person_id is not None, (
            f"Asset {asset.asset_code} status={asset.status} has no holder; "
            "seed data is inconsistent."
        )
        holder = holders_by_id[asset.responsible_person_id]
        histories.append(
            AssetActionHistory(
                asset_id=asset.id,
                actor_id=default_manager.id,
                action=AssetAction.ASSIGN,
                from_status=AssetStatus.IN_STOCK,
                to_status=AssetStatus.IN_USE,
                event_metadata={
                    "responsible_person_id": holder.id,
                    "responsible_person_name": holder.name,
                },
                created_at=base - timedelta(days=30),
            )
        )

        repair_request = repair_requests_by_asset.get(asset.id)
        if repair_request is None:
            continue

        reviewer = (
            managers_by_id.get(repair_request.reviewer_id, default_manager)
            if repair_request.reviewer_id is not None
            else default_manager
        )

        histories.append(
            AssetActionHistory(
                asset_id=asset.id,
                actor_id=holder.id,
                action=AssetAction.SUBMIT_REPAIR,
                from_status=AssetStatus.IN_USE,
                to_status=AssetStatus.PENDING_REPAIR,
                event_metadata={
                    "repair_request_id": repair_request.id,
                    "fault_description": repair_request.fault_description,
                },
                created_at=base - timedelta(days=5),
            )
        )

        if repair_request.status is RepairRequestStatus.PENDING_REVIEW:
            continue

        if repair_request.status is RepairRequestStatus.REJECTED:
            histories.append(
                AssetActionHistory(
                    asset_id=asset.id,
                    actor_id=reviewer.id,
                    action=AssetAction.REJECT_REPAIR,
                    from_status=AssetStatus.PENDING_REPAIR,
                    to_status=AssetStatus.IN_USE,
                    event_metadata={
                        "repair_request_id": repair_request.id,
                        "rejection_reason": repair_request.rejection_reason,
                    },
                    created_at=base - timedelta(days=4),
                )
            )
            continue

        # UNDER_REPAIR and COMPLETED both pass through APPROVE_REPAIR.
        histories.append(
            AssetActionHistory(
                asset_id=asset.id,
                actor_id=reviewer.id,
                action=AssetAction.APPROVE_REPAIR,
                from_status=AssetStatus.PENDING_REPAIR,
                to_status=AssetStatus.UNDER_REPAIR,
                event_metadata={"repair_request_id": repair_request.id},
                created_at=base - timedelta(days=4),
            )
        )

        if repair_request.status is RepairRequestStatus.COMPLETED:
            histories.append(
                AssetActionHistory(
                    asset_id=asset.id,
                    actor_id=reviewer.id,
                    action=AssetAction.COMPLETE_REPAIR,
                    from_status=AssetStatus.UNDER_REPAIR,
                    to_status=AssetStatus.IN_USE,
                    event_metadata={
                        "repair_request_id": repair_request.id,
                        # Decimal → str for deterministic JSON encoding; matches
                        # the writer in ``endpoints/repair_requests.py``.
                        "repair_cost": str(repair_request.repair_cost),
                        "repair_vendor": repair_request.repair_vendor,
                    },
                    created_at=base - timedelta(days=1),
                )
            )

    return histories


def main() -> None:
    if os.environ.get("AMS_SEED_CONFIRM") != "1":
        logger.error(
            "Set AMS_SEED_CONFIRM=1 to confirm seeding. "
            "This operation deletes ALL data in the target database."
        )
        sys.exit(1)

    with SessionLocal() as session:
        try:
            session.execute(delete(RepairImage))
            session.execute(delete(RepairRequest))
            # Explicit even though ``assets.id`` FK is ON DELETE CASCADE — keeps
            # the wipe order self-evident and survives future schema changes that
            # might loosen the cascade.
            session.execute(delete(AssetActionHistory))
            session.execute(delete(Asset))
            session.execute(delete(User))

            users = build_users()
            session.add_all(users)
            session.flush()

            managers = [user for user in users if user.role == UserRole.MANAGER]
            holders = [user for user in users if user.role == UserRole.HOLDER]

            assets = build_assets(holders)
            session.add_all(assets)
            session.flush()

            repair_requests = build_repair_requests(assets, holders, managers)
            session.add_all(repair_requests)
            session.flush()

            images = build_images(repair_requests)
            session.add_all(images)

            action_histories = build_action_histories(assets, repair_requests, holders, managers)
            session.add_all(action_histories)

            session.commit()
            logger.info("Seed complete:")
            logger.info("  users: %d", len(users))
            logger.info("  assets: %d", len(assets))
            logger.info("  repair_requests: %d", len(repair_requests))
            logger.info("  repair_images: %d", len(images))
            logger.info("  asset_action_histories: %d", len(action_histories))
        except Exception:
            session.rollback()
            logger.error("Seed failed. Database has been rolled back.", exc_info=True)
            sys.exit(1)


if __name__ == "__main__":
    main()
