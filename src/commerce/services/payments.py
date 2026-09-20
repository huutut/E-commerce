from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote_plus
from uuid import uuid4

from sqlmodel import Session, select

from commerce.core.config import get_settings
from commerce.domain.models import Order, OrderStatus, Payment, PaymentStatus, WebhookEvent


class PaymentNotAllowedError(ValueError):
    pass


class PaymentWebhookError(ValueError):
    pass


def simulate_payment(session: Session, order: Order) -> Payment:
    if order.status != OrderStatus.CREATED:
        raise PaymentNotAllowedError("Only created orders can be paid.")

    payment = Payment(
        order_id=order.id,
        provider="mock",
        status=PaymentStatus.SUCCEEDED,
        amount=order.total_amount,
        currency=order.currency,
        reference=f"MOCK-{uuid4().hex[:12].upper()}",
        live_mode=False,
        provider_payload={"source": "admin_mock"},
    )
    order.status = OrderStatus.PAID
    session.add(order)
    session.add(payment)
    return payment


def create_payment_session(
    session: Session,
    order: Order,
    *,
    provider: str | None = None,
) -> Payment:
    if order.status != OrderStatus.CREATED:
        raise PaymentNotAllowedError("Only created orders can start a payment.")

    settings = get_settings()
    provider_name = (provider or settings.payment_provider).strip().lower() or "mock"
    reference = f"{provider_name.upper()}-{uuid4().hex[:16].upper()}"
    checkout_url = _checkout_url(provider_name, order, reference)
    payment = Payment(
        order_id=order.id,
        provider=provider_name,
        status=PaymentStatus.PENDING,
        amount=order.total_amount,
        currency=order.currency,
        reference=reference,
        checkout_url=checkout_url,
        live_mode=settings.payment_live_mode,
        provider_payload={
            "order_id": str(order.id),
            "amount": str(order.total_amount),
            "currency": order.currency,
            "provider": provider_name,
        },
    )
    session.add(payment)
    return payment


def apply_payment_webhook(
    session: Session,
    *,
    provider: str,
    event_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> bool:
    event = WebhookEvent(
        provider=provider,
        event_id=event_id,
        event_type=event_type,
        payload=payload,
    )
    session.add(event)
    reference = _payload_text(payload, "reference")
    status = _payload_text(payload, "status")
    if not reference or not status:
        raise PaymentWebhookError("Webhook payload must include reference and status.")

    payment = session.exec(select(Payment).where(Payment.reference == reference)).first()
    if payment is None:
        raise PaymentWebhookError("Payment reference does not exist.")

    if status == "succeeded":
        payment.status = PaymentStatus.SUCCEEDED
        order = session.get(Order, payment.order_id)
        if order is not None and order.status == OrderStatus.CREATED:
            order.status = OrderStatus.PAID
            session.add(order)
    elif status == "failed":
        payment.status = PaymentStatus.FAILED
    elif status == "refunded":
        payment.status = PaymentStatus.REFUNDED
    else:
        raise PaymentWebhookError("Unsupported payment status.")

    event.processed_at = datetime.now(UTC)
    session.add(payment)
    session.add(event)
    return True


def _checkout_url(provider: str, order: Order, reference: str) -> str:
    settings = get_settings()
    base_url = settings.public_base_url.rstrip("/")
    if provider == "mock":
        return f"{base_url}/store/orders/{order.id}?payment_reference={quote_plus(reference)}"
    if provider == "stripe":
        return (
            f"{base_url}/store/orders/{order.id}?payment_provider=stripe"
            f"&reference={quote_plus(reference)}"
        )
    if provider in {"wechat_pay", "alipay"}:
        return (
            f"{base_url}/store/orders/{order.id}?payment_provider={provider}"
            f"&reference={quote_plus(reference)}"
        )
    return (
        f"{base_url}/store/orders/{order.id}?payment_provider={provider}"
        f"&reference={quote_plus(reference)}"
    )


def _payload_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    return value if isinstance(value, str) else ""
