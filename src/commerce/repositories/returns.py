from uuid import UUID

from sqlmodel import Session, col, select

from commerce.domain.models import ReturnRequest


def list_returns_for_order(session: Session, order_id: UUID) -> list[ReturnRequest]:
    statement = (
        select(ReturnRequest)
        .where(ReturnRequest.order_id == order_id)
        .order_by(col(ReturnRequest.created_at).desc())
    )
    return list(session.exec(statement).all())
