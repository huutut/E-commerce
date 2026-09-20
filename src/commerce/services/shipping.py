from datetime import UTC, datetime
from urllib.parse import quote_plus

from sqlmodel import Session

from commerce.core.config import get_settings
from commerce.domain.models import Order, Shipment, ShipmentStatus
from commerce.repositories.shipments import get_shipment_by_tracking_number


def upsert_shipment(
    session: Session,
    *,
    order: Order,
    carrier: str,
    tracking_number: str,
) -> Shipment | None:
    clean_carrier = carrier.strip()
    clean_tracking_number = tracking_number.strip()
    if not clean_carrier or not clean_tracking_number:
        return None

    settings = get_settings()
    shipment = get_shipment_by_tracking_number(session, clean_tracking_number)
    tracking_url = f"{settings.shipping_tracking_base_url}{quote_plus(clean_tracking_number)}"
    if shipment is None:
        shipment = Shipment(
            order_id=order.id,
            provider=settings.shipping_provider,
            carrier=clean_carrier,
            tracking_number=clean_tracking_number,
            status=ShipmentStatus.CREATED,
            tracking_url=tracking_url,
            provider_reference=clean_tracking_number,
            latest_event="运单已登记，等待承运商更新轨迹。",
        )
    else:
        shipment.carrier = clean_carrier
        shipment.tracking_url = tracking_url
        shipment.updated_at = datetime.now(UTC)
    session.add(shipment)
    return shipment
