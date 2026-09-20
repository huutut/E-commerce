import json
from decimal import Decimal
from uuid import UUID

from redis import Redis
from sqlmodel import Session

from commerce.domain.models import ProductStatus
from commerce.domain.schemas import CartItemRead, CartItemWrite, CartRead
from commerce.repositories.products import get_product_by_sku

CART_TTL_SECONDS = 60 * 60 * 24 * 14


class CartNotAvailableError(RuntimeError):
    pass


class ProductUnavailableError(ValueError):
    pass


def _cart_key(customer_id: UUID) -> str:
    return f"cart:{customer_id}"


def _load_raw_cart(redis: Redis, customer_id: UUID) -> dict[str, int]:
    try:
        payload = redis.get(_cart_key(customer_id))
    except Exception as exc:  # Redis client raises multiple connection-specific exceptions.
        raise CartNotAvailableError("Redis is required for cart operations.") from exc
    if not payload:
        return {}
    decoded = json.loads(payload)
    return {str(sku): int(quantity) for sku, quantity in decoded.items()}


def _save_raw_cart(redis: Redis, customer_id: UUID, cart: dict[str, int]) -> None:
    try:
        redis.set(_cart_key(customer_id), json.dumps(cart), ex=CART_TTL_SECONDS)
    except Exception as exc:
        raise CartNotAvailableError("Redis is required for cart operations.") from exc


def add_item(session: Session, redis: Redis, customer_id: UUID, item: CartItemWrite) -> CartRead:
    product = get_product_by_sku(session, item.sku)
    if product is None or product.status != ProductStatus.ACTIVE:
        raise ProductUnavailableError(f"SKU {item.sku} is not available.")
    if product.stock_on_hand < item.quantity:
        raise ProductUnavailableError(f"SKU {item.sku} does not have enough stock.")

    cart = _load_raw_cart(redis, customer_id)
    cart[item.sku] = cart.get(item.sku, 0) + item.quantity
    _save_raw_cart(redis, customer_id, cart)
    return read_cart(session, redis, customer_id)


def read_cart(session: Session, redis: Redis, customer_id: UUID) -> CartRead:
    cart = _load_raw_cart(redis, customer_id)
    items: list[CartItemRead] = []
    total = Decimal("0.00")
    currency = "CNY"

    for sku, quantity in cart.items():
        product = get_product_by_sku(session, sku)
        if product is None:
            continue
        line_total = product.price * quantity
        total += line_total
        currency = product.currency
        items.append(
            CartItemRead(
                sku=product.sku,
                name=product.name,
                quantity=quantity,
                unit_price=product.price,
                line_total=line_total,
            )
        )

    return CartRead(customer_id=customer_id, items=items, total_amount=total, currency=currency)


def clear_cart(redis: Redis, customer_id: UUID) -> None:
    try:
        redis.delete(_cart_key(customer_id))
    except Exception as exc:
        raise CartNotAvailableError("Redis is required for cart operations.") from exc
