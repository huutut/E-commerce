from uuid import UUID

from sqlmodel import Session, col, select

from commerce.domain.models import Shipment


def list_shipments_for_order(session: Session, order_id: UUID) -> list[Shipment]:
    statement = (
        select(Shipment)
        .where(Shipment.order_id == order_id)
        .order_by(col(Shipment.created_at).desc())
    )
    return list(session.exec(statement).all())


def get_shipment_by_tracking_number(session: Session, tracking_number: str) -> Shipment | None:
    statement = select(Shipment).where(Shipment.tracking_number == tracking_number)
    return session.exec(statement).first()
