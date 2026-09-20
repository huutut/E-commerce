from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from commerce.api.deps import RedisDep, SessionDep, api_key_dep
from commerce.domain.schemas import CartItemWrite, CartRead
from commerce.services.cart import (
    CartNotAvailableError,
    ProductUnavailableError,
    add_item,
    clear_cart,
    read_cart,
)

router = APIRouter(prefix="/cart", tags=["cart"], dependencies=[Depends(api_key_dep)])


@router.post("/{customer_id}/items", response_model=CartRead)
def add_cart_item(
    customer_id: UUID,
    payload: CartItemWrite,
    session: SessionDep,
    redis: RedisDep,
) -> CartRead:
    try:
        return add_item(session, redis, customer_id, payload)
    except ProductUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CartNotAvailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/{customer_id}", response_model=CartRead)
def get_cart(
    customer_id: UUID,
    session: SessionDep,
    redis: RedisDep,
) -> CartRead:
    try:
        return read_cart(session, redis, customer_id)
    except CartNotAvailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cart(customer_id: UUID, redis: RedisDep) -> None:
    try:
        clear_cart(redis, customer_id)
    except CartNotAvailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
