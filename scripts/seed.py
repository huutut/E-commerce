from decimal import Decimal
from typing import TypedDict

from sqlmodel import Session, select

from commerce.core.database import get_engine
from commerce.domain.models import AdminRole, AdminUser, ApiKey, Product, ProductStatus
from commerce.repositories.admins import get_admin_by_email
from commerce.repositories.products import get_product_by_sku
from commerce.services.security import hash_api_key, hash_password


class SeedProduct(TypedDict):
    sku: str
    name: str
    description: str
    category: str
    price: Decimal
    stock_on_hand: int
    low_stock_threshold: int


SEED_PRODUCTS: list[SeedProduct] = [
    {
        "sku": "KEYBOARD-001",
        "name": "低轴机械键盘",
        "description": "适合长时间办公和开发的热插拔机械键盘。",
        "category": "数码办公",
        "price": Decimal("399.00"),
        "stock_on_hand": 50,
        "low_stock_threshold": 10,
    },
    {
        "sku": "MOUSE-001",
        "name": "人体工学无线鼠标",
        "description": "轻量化静音按键鼠标，适合日常办公。",
        "category": "数码办公",
        "price": Decimal("169.00"),
        "stock_on_hand": 8,
        "low_stock_threshold": 10,
    },
]
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "Admin@123456"
DEV_API_KEY = "ck_live_dev.local-development-api-key"


def main() -> None:
    with Session(get_engine()) as session:
        admin = get_admin_by_email(session, ADMIN_EMAIL)
        if admin is None:
            session.add(
                AdminUser(
                    email=ADMIN_EMAIL,
                    full_name="系统管理员",
                    password_hash=hash_password(ADMIN_PASSWORD),
                    role=AdminRole.OWNER,
                )
            )

        api_key = session.exec(
            select(ApiKey).where(ApiKey.key_prefix == "ck_live_dev")
        ).first()
        if api_key is None:
            session.add(
                ApiKey(
                    name="本地开发 API Key",
                    key_prefix="ck_live_dev",
                    key_hash=hash_api_key(DEV_API_KEY),
                    created_by_email=ADMIN_EMAIL,
                )
            )

        for data in SEED_PRODUCTS:
            product = get_product_by_sku(session, data["sku"])
            if product is not None:
                product.name = data["name"]
                product.description = data["description"]
                product.category = data["category"]
                product.price = data["price"]
                product.stock_on_hand = data["stock_on_hand"]
                product.low_stock_threshold = data["low_stock_threshold"]
                product.currency = "CNY"
                product.status = ProductStatus.ACTIVE
                session.add(product)
                continue
            session.add(Product(**data, currency="CNY", status=ProductStatus.ACTIVE))
        session.commit()
    print("Seed data loaded.")
    print(f"Admin login: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    print(f"API key: {DEV_API_KEY}")


if __name__ == "__main__":
    main()
