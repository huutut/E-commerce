from uuid import UUID

from sqlmodel import Session, col, select

from commerce.domain.models import Payment


def list_payments_for_order(session: Session, order_id: UUID) -> list[Payment]:
    statement = (
        select(Payment)
        .where(Payment.order_id == order_id)
        .order_by(col(Payment.created_at).desc())
    )
    return list(session.exec(statement).all())
