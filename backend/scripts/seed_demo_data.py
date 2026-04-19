from __future__ import annotations

import logging
import os
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete

from app.db.session import SessionLocal
from app.models.asset import Asset, AssetStatus
from app.models.repair_image import RepairImage
from app.models.repair_request import RepairRequest, RepairRequestStatus
from app.models.user import User, UserRole

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEPARTMENTS = ["IT", "HR", "Finance", "Operations"]
LOCATIONS = ["Taipei HQ", "Hsinchu Office", "Taichung Branch"]
SUPPLIERS = ["Apple", "Dell", "Lenovo", "ASUS", "Samsung"]
CATEGORIES = ["Laptop", "Phone", "Tablet", "Monitor", "Accessory"]
ASSET_NAMES = {
    "Laptop": "Business Laptop",
    "Phone": "Company Phone",
    "Tablet": "Field Tablet",
    "Monitor": "Office Monitor",
    "Accessory": "Docking Station",
}
MODELS = {
    "Laptop": ["Dell Latitude 7440", "MacBook Pro 14", "ThinkPad T14"],
    "Phone": ["iPhone 15", "Galaxy S24", "Pixel 9"],
    "Tablet": ["iPad Air", "Galaxy Tab S9", "Surface Go 4"],
    "Monitor": ["Dell U2723QE", "LG 27UP850", "ASUS ProArt 27"],
    "Accessory": ["Dell WD22TB4", "Anker Hub 565", "Lenovo Dock Gen 2"],
}
FAULT_DESCRIPTIONS = [
    "Screen flickers intermittently during work.",
    "Battery drains unusually fast after charging.",
    "Device overheats when running normal office apps.",
    "Wi-Fi disconnects several times a day.",
    "Keyboard keys sometimes stop responding.",
]


def hash_password(password: str) -> str:
    import bcrypt

    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def build_users() -> list[User]:
    users: list[User] = []
    for index in range(2):
        users.append(
            User(
                email=f"manager{index + 1}@example.com",
                password_hash=hash_password("Password123"),
                name=f"Manager {index + 1}",
                role=UserRole.MANAGER,
                department=DEPARTMENTS[index],
            )
        )
    for index in range(2):
        users.append(
            User(
                email=f"holder{index + 1}@example.com",
                password_hash=hash_password("Password123"),
                name=f"Holder {index + 1}",
                role=UserRole.HOLDER,
                department=DEPARTMENTS[index + 2],
            )
        )
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
            f"IN_USE asset {asset.asset_code} has no responsible_person_id; seed data is inconsistent."
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
    for index, request in enumerate(repair_requests[:6]):
        images.append(
            RepairImage(
                repair_request_id=request.id,
                image_url=f"/uploads/demo/repair-{index + 1}.jpg",
            )
        )
    return images


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

            session.commit()
            logger.info("Seed complete:")
            logger.info("  users: %d", len(users))
            logger.info("  assets: %d", len(assets))
            logger.info("  repair_requests: %d", len(repair_requests))
            logger.info("  repair_images: %d", len(images))
        except Exception:
            session.rollback()
            logger.error("Seed failed. Database has been rolled back.", exc_info=True)
            sys.exit(1)


if __name__ == "__main__":
    main()
