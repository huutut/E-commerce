from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import String, cast, func
from sqlmodel import Session, col, select

from commerce.domain.models import Customer, Order, OrderStatus


@dataclass(frozen=True)
class OrderSummary:
    order: Order
    customer: Customer


@dataclass(frozen=True)
class OrderStatusCount:
    status: OrderStatus
    count: int


def list_recent_orders(
    session: Session,
    *,
    status: OrderStatus | None = None,
    limit: int = 50,
) -> list[Order]:
    statement = select(Order)
    if status:
        statement = statement.where(Order.status == status)
    statement = statement.order_by(col(Order.created_at).desc()).limit(limit)
    return list(session.exec(statement).all())


def list_order_summaries(
    session: Session,
    *,
    query: str | None = None,
    status: OrderStatus | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    limit: int = 100,
) -> list[OrderSummary]:
    statement = select(Order, Customer).join(Customer, col(Order.customer_id) == col(Customer.id))
    if query:
        search = f"%{query.strip()}%"
        statement = statement.where(
            cast(Order.id, String).ilike(search)
            | col(Customer.email).ilike(search)
            | col(Customer.full_name).ilike(search)
        )
    if status:
        statement = statement.where(Order.status == status)
    if created_from:
        statement = statement.where(Order.created_at >= created_from)
    if created_to:
        statement = statement.where(Order.created_at <= created_to)
    statement = statement.order_by(col(Order.created_at).desc()).limit(limit)
    return [
        OrderSummary(order=order, customer=customer)
        for order, customer in session.exec(statement)
    ]


def list_orders_for_customer(
    session: Session,
    customer_id: UUID,
    *,
    limit: int = 50,
) -> list[Order]:
    statement = (
        select(Order)
        .where(Order.customer_id == customer_id)
        .order_by(col(Order.created_at).desc())
        .limit(limit)
    )
    return list(session.exec(statement).all())


def count_orders(session: Session) -> int:
    return len(session.exec(select(Order.id)).all())


def sum_order_revenue(session: Session) -> Decimal:
    statement = select(func.coalesce(func.sum(Order.total_amount), 0))
    value = session.exec(statement).one()
    return Decimal(value)


def count_orders_by_status(session: Session) -> list[OrderStatusCount]:
    statement = select(Order.status, func.count(col(Order.id))).group_by(Order.status)
    return [
        OrderStatusCount(status=OrderStatus(status), count=int(count))
        for status, count in session.exec(statement)
    ]
