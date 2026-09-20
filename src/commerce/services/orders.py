from decimal import Decimal
from uuid import UUID

from redis import Redis
from sqlmodel import Session, select

from commerce.domain.models import Customer, Order, OrderLine, OrderStatus
from commerce.domain.schemas import OrderLineRead, OrderRead
from commerce.repositories.products import get_product_by_sku
from commerce.services.cart import ProductUnavailableError, clear_cart, read_cart


class CustomerNotFoundError(ValueError):
    pass


class EmptyCartError(ValueError):
    pass


class InvalidOrderTransitionError(ValueError):
    pass


ALLOWED_ORDER_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.CREATED: {OrderStatus.PAID, OrderStatus.CANCELLED},
    OrderStatus.PAID: {OrderStatus.FULFILLED, OrderStatus.CANCELLED},
    OrderStatus.FULFILLED: set(),
    OrderStatus.CANCELLED: set(),
}


def checkout(session: Session, redis: Redis, customer_id: UUID) -> OrderRead:
    customer = session.get(Customer, customer_id)
    if customer is None:
        raise CustomerNotFoundError("Customer does not exist.")

    cart = read_cart(session, redis, customer_id)
    if not cart.items:
        raise EmptyCartError("Cart is empty.")

    order = Order(
        customer_id=customer_id,
        status=OrderStatus.CREATED,
        total_amount=cart.total_amount,
        currency=cart.currency,
    )
    session.add(order)
    session.flush()

    for item in cart.items:
        product = get_product_by_sku(session, item.sku)
        if product is None or product.stock_on_hand < item.quantity:
            raise ProductUnavailableError(f"SKU {item.sku} does not have enough stock.")
        product.stock_on_hand -= item.quantity
        line = OrderLine(
            order_id=order.id,
            product_id=product.id,
            sku=product.sku,
            name=product.name,
            quantity=item.quantity,
            unit_price=product.price,
            line_total=product.price * item.quantity,
        )
        session.add(product)
        session.add(line)

    session.commit()
    session.refresh(order)
    clear_cart(redis, customer_id)
    return get_order(session, order.id)


def get_order(session: Session, order_id: UUID) -> OrderRead:
    order = session.get(Order, order_id)
    if order is None:
        raise LookupError("Order does not exist.")
    lines = session.exec(select(OrderLine).where(OrderLine.order_id == order_id)).all()
    return _to_order_read(order, list(lines))


def update_order_status(session: Session, order_id: UUID, target_status: OrderStatus) -> OrderRead:
    order = session.get(Order, order_id)
    if order is None:
        raise LookupError("Order does not exist.")
    allowed_targets = ALLOWED_ORDER_TRANSITIONS[order.status]
    if target_status not in allowed_targets:
        raise InvalidOrderTransitionError(
            f"Cannot change order from {order.status.value} to {target_status.value}."
        )

    order.status = target_status
    session.add(order)
    session.commit()
    session.refresh(order)
    return get_order(session, order_id)


def _to_order_read(order: Order, lines: list[OrderLine]) -> OrderRead:
    return OrderRead(
        id=order.id,
        customer_id=order.customer_id,
        status=order.status,
        total_amount=Decimal(order.total_amount),
        currency=order.currency,
        note=order.note,
        shipping_carrier=order.shipping_carrier,
        tracking_number=order.tracking_number,
        shipped_at=order.shipped_at,
        lines=[
            OrderLineRead(
                sku=line.sku,
                name=line.name,
                quantity=line.quantity,
                unit_price=Decimal(line.unit_price),
                line_total=Decimal(line.line_total),
            )
            for line in lines
        ],
    )
