from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from commerce.api.deps import RedisDep, SessionDep, api_key_dep
from commerce.domain.schemas import CheckoutRequest, OrderRead
from commerce.services.cart import CartNotAvailableError, ProductUnavailableError
from commerce.services.orders import CustomerNotFoundError, EmptyCartError, checkout, get_order

router = APIRouter(prefix="/orders", tags=["orders"], dependencies=[Depends(api_key_dep)])


@router.post("/checkout", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
def checkout_order(
    payload: CheckoutRequest,
    session: SessionDep,
    redis: RedisDep,
) -> OrderRead:
    try:
        return checkout(session, redis, payload.customer_id)
    except CustomerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EmptyCartError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ProductUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CartNotAvailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/{order_id}", response_model=OrderRead)
def read_order(order_id: UUID, session: SessionDep) -> OrderRead:
    try:
        return get_order(session, order_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
