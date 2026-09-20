from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError

from commerce.api.deps import SessionDep, api_key_dep
from commerce.domain.models import Product
from commerce.domain.schemas import ProductCreate, ProductRead
from commerce.repositories.products import get_product_by_sku, list_active_products

router = APIRouter(prefix="/products", tags=["products"], dependencies=[Depends(api_key_dep)])


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, session: SessionDep) -> Product:
    product = Product.model_validate(payload)
    session.add(product)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Product SKU already exists.") from exc
    session.refresh(product)
    return product


@router.get("", response_model=list[ProductRead])
def list_products(
    session: SessionDep,
    q: str | None = None,
    category: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Product]:
    return list_active_products(session, query=q, category=category, limit=limit, offset=offset)


@router.get("/{sku}", response_model=ProductRead)
def get_product(sku: str, session: SessionDep) -> Product:
    product = get_product_by_sku(session, sku)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found.")
    return product
