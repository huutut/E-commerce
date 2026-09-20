from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func
from sqlmodel import Session, col, select

from commerce.domain.models import Customer, Order


@dataclass(frozen=True)
class CustomerSummary:
    id: UUID
    email: str
    full_name: str
    created_at: datetime
    order_count: int
    total_spent: Decimal
    last_order_at: datetime | None


def get_customer_by_email(session: Session, email: str) -> Customer | None:
    statement = select(Customer).where(Customer.email == email)
    return session.exec(statement).first()


def list_recent_customers(session: Session, *, limit: int = 20) -> list[Customer]:
    statement = select(Customer).order_by(col(Customer.created_at).desc()).limit(limit)
    return list(session.exec(statement).all())


def list_customer_summaries(
    session: Session,
    *,
    query: str | None = None,
    limit: int = 100,
) -> list[CustomerSummary]:
    statement = (
        select(
            Customer,
            func.count(col(Order.id)),
            func.coalesce(func.sum(col(Order.total_amount)), 0),
            func.max(col(Order.created_at)),
        )
        .join(Order, col(Customer.id) == col(Order.customer_id), isouter=True)
    )
    if query:
        search = f"%{query}%"
        statement = statement.where(
            col(Customer.email).ilike(search) | col(Customer.full_name).ilike(search)
        )
    statement = (
        statement.group_by(col(Customer.id))
        .order_by(col(Customer.created_at).desc())
        .limit(limit)
    )
    rows = session.exec(statement).all()
    return [
        CustomerSummary(
            id=customer.id,
            email=customer.email,
            full_name=customer.full_name,
            created_at=customer.created_at,
            order_count=int(order_count),
            total_spent=Decimal(total_spent),
            last_order_at=last_order_at,
        )
        for customer, order_count, total_spent, last_order_at in rows
    ]


def count_customers(session: Session) -> int:
    return len(session.exec(select(Customer.id)).all())
