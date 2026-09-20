from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from commerce.domain.models import OrderStatus, ProductStatus


class CustomerCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)


class CustomerRead(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str


class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    image_url: str = Field(default="", max_length=500)
    category: str = Field(min_length=1, max_length=120)
    price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    stock_on_hand: int = Field(default=0, ge=0)
    low_stock_threshold: int = Field(default=10, ge=0)
    status: ProductStatus = ProductStatus.ACTIVE


class ProductRead(ProductCreate):
    id: UUID


class CartItemWrite(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    quantity: int = Field(gt=0, le=999)


class CartItemRead(BaseModel):
    sku: str
    name: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class CartRead(BaseModel):
    customer_id: UUID
    items: list[CartItemRead]
    total_amount: Decimal
    currency: str = "CNY"


class CheckoutRequest(BaseModel):
    customer_id: UUID


class OrderLineRead(BaseModel):
    sku: str
    name: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class OrderRead(BaseModel):
    id: UUID
    customer_id: UUID
    status: OrderStatus
    total_amount: Decimal
    currency: str
    note: str = ""
    shipping_carrier: str = ""
    tracking_number: str = ""
    shipped_at: datetime | None = None
    lines: list[OrderLineRead]
