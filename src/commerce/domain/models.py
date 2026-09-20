from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, Column, DateTime, Numeric, UniqueConstraint
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(UTC)


class ProductStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class OrderStatus(StrEnum):
    CREATED = "created"
    PAID = "paid"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


class ReturnStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    COMPLETED = "completed"
    REJECTED = "rejected"


class ShipmentStatus(StrEnum):
    PENDING = "pending"
    CREATED = "created"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    EXCEPTION = "exception"


class AdminRole(StrEnum):
    OWNER = "owner"
    OPERATOR = "operator"


class Customer(SQLModel, table=True):
    __tablename__ = "customers"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(index=True, unique=True, max_length=320)
    full_name: str = Field(max_length=200)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class Product(SQLModel, table=True):
    __tablename__ = "products"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    sku: str = Field(index=True, unique=True, max_length=64)
    name: str = Field(index=True, max_length=200)
    description: str = Field(default="", max_length=2000)
    image_url: str = Field(default="", max_length=500)
    category: str = Field(index=True, max_length=120)
    price: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    currency: str = Field(default="CNY", max_length=3)
    stock_on_hand: int = Field(default=0, ge=0)
    low_stock_threshold: int = Field(default=10, ge=0)
    status: ProductStatus = Field(default=ProductStatus.DRAFT, index=True)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class Order(SQLModel, table=True):
    __tablename__ = "orders"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    customer_id: UUID = Field(foreign_key="customers.id", index=True)
    status: OrderStatus = Field(default=OrderStatus.CREATED, index=True)
    total_amount: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    currency: str = Field(default="CNY", max_length=3)
    note: str = Field(default="", max_length=500)
    shipping_carrier: str = Field(default="", max_length=120)
    tracking_number: str = Field(default="", max_length=120)
    shipped_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class OrderLine(SQLModel, table=True):
    __tablename__ = "order_lines"
    __table_args__ = (UniqueConstraint("order_id", "sku", name="uq_order_line_order_sku"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    order_id: UUID = Field(foreign_key="orders.id", index=True)
    product_id: UUID = Field(foreign_key="products.id")
    sku: str = Field(index=True, max_length=64)
    name: str = Field(max_length=200)
    quantity: int = Field(gt=0)
    unit_price: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    line_total: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))


class Payment(SQLModel, table=True):
    __tablename__ = "payments"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    order_id: UUID = Field(foreign_key="orders.id", index=True)
    provider: str = Field(default="mock", max_length=60)
    status: PaymentStatus = Field(default=PaymentStatus.PENDING, index=True)
    amount: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    currency: str = Field(default="CNY", max_length=3)
    reference: str = Field(default="", index=True, max_length=120)
    checkout_url: str = Field(default="", max_length=1000)
    live_mode: bool = Field(default=False, sa_column=Column(Boolean, nullable=False))
    provider_payload: dict[str, object] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class Shipment(SQLModel, table=True):
    __tablename__ = "shipments"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    order_id: UUID = Field(foreign_key="orders.id", index=True)
    provider: str = Field(default="manual", max_length=60)
    carrier: str = Field(max_length=120)
    tracking_number: str = Field(index=True, max_length=120)
    status: ShipmentStatus = Field(default=ShipmentStatus.CREATED, index=True)
    tracking_url: str = Field(default="", max_length=1000)
    provider_reference: str = Field(default="", index=True, max_length=120)
    latest_event: str = Field(default="", max_length=500)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class WebhookEvent(SQLModel, table=True):
    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    provider: str = Field(index=True, max_length=60)
    event_id: str = Field(index=True, max_length=160)
    event_type: str = Field(index=True, max_length=160)
    payload: dict[str, object] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    processed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class ReturnRequest(SQLModel, table=True):
    __tablename__ = "return_requests"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    order_id: UUID = Field(foreign_key="orders.id", index=True)
    status: ReturnStatus = Field(default=ReturnStatus.REQUESTED, index=True)
    reason: str = Field(max_length=500)
    resolution_note: str = Field(default="", max_length=500)
    created_by_id: UUID | None = Field(default=None, foreign_key="admin_users.id", index=True)
    created_by_email: str = Field(max_length=320)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class AdminUser(SQLModel, table=True):
    __tablename__ = "admin_users"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(index=True, unique=True, max_length=320)
    full_name: str = Field(max_length=200)
    password_hash: str = Field(max_length=256)
    role: AdminRole = Field(default=AdminRole.OPERATOR, index=True)
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    actor_id: UUID | None = Field(default=None, foreign_key="admin_users.id", index=True)
    actor_email: str = Field(max_length=320)
    action: str = Field(index=True, max_length=120)
    entity_type: str = Field(index=True, max_length=120)
    entity_id: str = Field(index=True, max_length=120)
    summary: str = Field(max_length=500)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class InventoryAdjustment(SQLModel, table=True):
    __tablename__ = "inventory_adjustments"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    product_id: UUID = Field(foreign_key="products.id", index=True)
    sku: str = Field(index=True, max_length=64)
    actor_id: UUID | None = Field(default=None, foreign_key="admin_users.id", index=True)
    actor_email: str = Field(max_length=320)
    change_quantity: int
    stock_before: int
    stock_after: int
    reason: str = Field(max_length=500)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class ApiKey(SQLModel, table=True):
    __tablename__ = "api_keys"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=120)
    key_prefix: str = Field(index=True, unique=True, max_length=24)
    key_hash: str = Field(max_length=128)
    created_by_id: UUID | None = Field(default=None, foreign_key="admin_users.id", index=True)
    created_by_email: str = Field(max_length=320)
    is_active: bool = Field(default=True, index=True)
    last_used_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class ApiAccessLog(SQLModel, table=True):
    __tablename__ = "api_access_logs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    api_key_id: UUID | None = Field(default=None, foreign_key="api_keys.id", index=True)
    key_prefix: str = Field(default="", index=True, max_length=24)
    method: str = Field(max_length=12)
    path: str = Field(index=True, max_length=300)
    status: str = Field(index=True, max_length=40)
    status_code: int
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
