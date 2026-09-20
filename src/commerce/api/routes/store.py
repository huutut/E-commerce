from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from commerce.api.deps import RedisDep, SessionDep
from commerce.domain.models import Customer, Order, OrderLine
from commerce.domain.schemas import CartItemWrite
from commerce.repositories.customers import get_customer_by_email
from commerce.repositories.products import list_active_products
from commerce.services.cart import (
    CartNotAvailableError,
    ProductUnavailableError,
    add_item,
    read_cart,
)
from commerce.services.orders import (
    CustomerNotFoundError,
    EmptyCartError,
    checkout,
    get_order,
)
from commerce.services.payments import PaymentNotAllowedError, create_payment_session

router = APIRouter(tags=["store"])
templates = Environment(
    loader=FileSystemLoader("src/commerce/templates"),
    autoescape=select_autoescape(["html"]),
)


@router.get("/", response_class=HTMLResponse)
@router.get("/store", response_class=HTMLResponse)
def storefront(
    request: Request,
    session: SessionDep,
    redis: RedisDep,
    q: str | None = None,
    category: str | None = None,
    email: str | None = None,
) -> HTMLResponse:
    customer = get_customer_by_email(session, email.strip().lower()) if email else None
    cart = None
    if customer is not None:
        try:
            cart = read_cart(session, redis, customer.id)
        except CartNotAvailableError:
            cart = None
    return _render(
        "store/home.html",
        request=request,
        products=list_active_products(session, query=q, category=category, limit=48),
        filters={"q": q or "", "category": category or "", "email": email or ""},
        customer=customer,
        cart=cart,
        error=request.query_params.get("error") or "",
    )


@router.post("/store/customers")
def create_or_load_store_customer(
    session: SessionDep,
    email: Annotated[str, Form(...)],
    full_name: Annotated[str, Form(...)],
) -> RedirectResponse:
    normalized_email = email.strip().lower()
    customer = get_customer_by_email(session, normalized_email)
    if customer is None:
        customer = Customer(email=normalized_email, full_name=full_name.strip())
        session.add(customer)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
    return _redirect(f"/store?email={normalized_email}")


@router.post("/store/cart")
def add_store_cart_item(
    session: SessionDep,
    redis: RedisDep,
    customer_id: Annotated[UUID, Form(...)],
    email: Annotated[str, Form(...)],
    sku: Annotated[str, Form(...)],
    quantity: Annotated[int, Form(...)],
) -> RedirectResponse:
    try:
        add_item(session, redis, customer_id, CartItemWrite(sku=sku, quantity=quantity))
    except ProductUnavailableError:
        return _redirect(f"/store?email={email}&error=stock")
    except CartNotAvailableError:
        return _redirect(f"/store?email={email}&error=cart")
    return _redirect(f"/store?email={email}")


@router.post("/store/checkout")
def checkout_store_cart(
    session: SessionDep,
    redis: RedisDep,
    customer_id: Annotated[UUID, Form(...)],
    email: Annotated[str, Form(...)],
) -> RedirectResponse:
    try:
        order = checkout(session, redis, customer_id)
    except (CustomerNotFoundError, EmptyCartError, ProductUnavailableError):
        return _redirect(f"/store?email={email}&error=checkout")
    except CartNotAvailableError:
        return _redirect(f"/store?email={email}&error=cart")
    return _redirect(f"/store/orders/{order.id}")


@router.get("/store/orders/{order_id}", response_class=HTMLResponse)
def store_order_detail(order_id: UUID, request: Request, session: SessionDep) -> HTMLResponse:
    order = get_order(session, order_id)
    lines = session.exec(select(OrderLine).where(OrderLine.order_id == order_id)).all()
    return _render(
        "store/order_detail.html",
        request=request,
        order=order,
        lines=lines,
        payment_created=bool(request.query_params.get("payment_created")),
    )


@router.post("/store/orders/{order_id}/payments")
def create_store_payment(order_id: UUID, session: SessionDep) -> RedirectResponse:
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    try:
        payment = create_payment_session(session, order)
    except PaymentNotAllowedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    return _redirect(payment.checkout_url or f"/store/orders/{order_id}?payment_created=1")


def _render(template_name: str, **context: object) -> HTMLResponse:
    template = templates.get_template(template_name)
    return HTMLResponse(template.render(**context))


def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)
