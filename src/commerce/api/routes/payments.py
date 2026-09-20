import hashlib
import hmac
import json
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError

from commerce.api.deps import SessionDep, api_key_dep
from commerce.core.config import get_settings
from commerce.domain.models import Order, Payment
from commerce.services.payments import (
    PaymentNotAllowedError,
    PaymentWebhookError,
    apply_payment_webhook,
    create_payment_session,
)

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post(
    "/orders/{order_id}/checkout",
    response_model=dict[str, object],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(api_key_dep)],
)
def create_order_payment_checkout(order_id: UUID, session: SessionDep) -> dict[str, object]:
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order does not exist.")
    try:
        payment = create_payment_session(session, order)
    except PaymentNotAllowedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    session.refresh(payment)
    return _payment_payload(payment)


@router.post("/webhooks/{provider}", response_model=dict[str, object])
async def receive_payment_webhook(
    provider: str,
    request: Request,
    session: SessionDep,
    x_commerce_signature: Annotated[str | None, Header(alias="X-Commerce-Signature")] = None,
) -> dict[str, object]:
    body = await request.body()
    _verify_signature(body, x_commerce_signature)
    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Webhook payload must be JSON.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Webhook payload must be an object.")

    event_id = _payload_text(payload, "event_id")
    event_type = _payload_text(payload, "event_type") or "payment.updated"
    if not event_id:
        raise HTTPException(status_code=400, detail="Webhook payload must include event_id.")
    try:
        processed = apply_payment_webhook(
            session,
            provider=provider,
            event_id=event_id,
            event_type=event_type,
            payload=payload,
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        return {"processed": False, "duplicate": True}
    except PaymentWebhookError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"processed": processed, "duplicate": False}


def _verify_signature(body: bytes, signature: str | None) -> None:
    secret = get_settings().payment_webhook_secret
    if not secret:
        return
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid webhook signature.")


def _payload_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    return value if isinstance(value, str) else ""


def _payment_payload(payment: Payment) -> dict[str, object]:
    return {
        "id": str(payment.id),
        "order_id": str(payment.order_id),
        "provider": payment.provider,
        "status": payment.status.value,
        "amount": str(payment.amount),
        "currency": payment.currency,
        "reference": payment.reference,
        "checkout_url": payment.checkout_url,
        "live_mode": payment.live_mode,
    }
