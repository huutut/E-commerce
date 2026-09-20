import csv
import re
from datetime import UTC, datetime, time
from decimal import Decimal, InvalidOperation
from io import StringIO
from pathlib import Path
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from commerce.api.deps import RedisDep, SessionDep
from commerce.core.config import get_settings
from commerce.domain.models import (
    AdminRole,
    AdminUser,
    ApiAccessLog,
    Customer,
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
    Product,
    ProductStatus,
    ReturnRequest,
    ReturnStatus,
)
from commerce.domain.schemas import CartItemWrite
from commerce.repositories.admins import get_admin_by_email, get_admin_by_id, list_admins
from commerce.repositories.api_access_logs import list_api_access_logs
from commerce.repositories.api_keys import create_api_key, get_api_key_by_id, list_api_keys
from commerce.repositories.audit import list_audit_logs, record_audit_log
from commerce.repositories.customers import (
    count_customers,
    get_customer_by_email,
    list_customer_summaries,
)
from commerce.repositories.inventory import adjust_inventory, list_inventory_adjustments
from commerce.repositories.orders import (
    count_orders,
    count_orders_by_status,
    list_order_summaries,
    list_orders_for_customer,
    list_recent_orders,
    sum_order_revenue,
)
from commerce.repositories.payments import list_payments_for_order
from commerce.repositories.products import (
    get_product_by_sku,
    list_active_products,
    list_low_stock_products,
    list_products,
)
from commerce.repositories.returns import list_returns_for_order
from commerce.repositories.shipments import list_shipments_for_order
from commerce.services.cart import (
    CartNotAvailableError,
    ProductUnavailableError,
    add_item,
    read_cart,
)
from commerce.services.orders import (
    ALLOWED_ORDER_TRANSITIONS,
    CustomerNotFoundError,
    EmptyCartError,
    InvalidOrderTransitionError,
    checkout,
    get_order,
    update_order_status,
)
from commerce.services.payments import PaymentNotAllowedError, simulate_payment
from commerce.services.permissions import (
    ROLE_PERMISSIONS,
    AdminPermission,
    admin_has_permission,
)
from commerce.services.security import (
    SESSION_COOKIE_NAME,
    authenticate_admin,
    create_session_cookie,
    hash_password,
    verify_password,
)
from commerce.services.shipping import upsert_shipment

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Environment(
    loader=FileSystemLoader("src/commerce/templates"),
    autoescape=select_autoescape(["html"]),
)
templates.filters["product_status_label"] = lambda status: {
    "draft": "草稿",
    "active": "上架",
    "archived": "归档",
}.get(_status_value(status), str(status))
templates.filters["order_status_label"] = lambda status: {
    "created": "已创建",
    "paid": "已支付",
    "fulfilled": "已履约",
    "cancelled": "已取消",
}.get(_status_value(status), str(status))
templates.filters["admin_role_label"] = lambda role: {
    "owner": "所有者",
    "operator": "运营员",
}.get(_status_value(role), str(role))
templates.filters["payment_status_label"] = lambda status: {
    "pending": "待处理",
    "succeeded": "成功",
    "failed": "失败",
    "refunded": "已退款",
}.get(_status_value(status), str(status))
templates.filters["return_status_label"] = lambda status: {
    "requested": "待处理",
    "approved": "已批准",
    "completed": "已完成",
    "rejected": "已拒绝",
}.get(_status_value(status), str(status))
SkuForm = Annotated[str, Form(...)]
NameForm = Annotated[str, Form(...)]
CategoryForm = Annotated[str, Form(...)]
PriceForm = Annotated[str, Form(...)]
QuantityForm = Annotated[int, Form(...)]
StockForm = Annotated[int, Form(...)]
ThresholdForm = Annotated[int, Form(...)]
InventoryChangeForm = Annotated[int, Form(...)]
DescriptionForm = Annotated[str, Form()]
ImageUrlForm = Annotated[str, Form()]
ReasonForm = Annotated[str, Form(...)]
OptionalTextForm = Annotated[str, Form()]
StatusForm = Annotated[ProductStatus, Form()]
OrderStatusForm = Annotated[OrderStatus, Form(...)]
EmailForm = Annotated[str, Form(...)]
CustomerIdForm = Annotated[UUID, Form(...)]
PasswordForm = Annotated[str, Form(...)]
NewPasswordForm = Annotated[str, Form(...)]
RoleForm = Annotated[AdminRole, Form(...)]
ActionForm = Annotated[str, Form(...)]
SearchQuery = Annotated[str | None, Query()]
CategoryQuery = Annotated[str | None, Query()]
ProductStatusQuery = Annotated[ProductStatus | None, Query()]
OrderStatusQuery = Annotated[OrderStatus | None, Query()]
LowStockQuery = Annotated[bool, Query()]
DateQuery = Annotated[str | None, Query()]


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return _render(
        "admin/login.html",
        request=request,
        error="1" if request.query_params.get("error") else "",
        next_path=request.query_params.get("next") or "/admin",
    )


@router.post("/login")
def login_from_form(
    session: SessionDep,
    email: EmailForm,
    password: PasswordForm,
    next_path: Annotated[str, Form()] = "/admin",
) -> RedirectResponse:
    normalized_email = email.strip().lower()
    admin = authenticate_admin(session, email, password)
    if admin is None:
        record_audit_log(
            session,
            actor=None,
            action="admin.login_failed",
            entity_type="admin_user",
            entity_id=normalized_email,
            summary=f"后台登录失败：{normalized_email}",
        )
        session.commit()
        return _redirect("/admin/login?error=1")

    record_audit_log(
        session,
        actor=admin,
        action="admin.login",
        entity_type="admin_user",
        entity_id=admin.id,
        summary=f"{admin.email} 登录后台",
    )
    session.commit()
    response = _redirect(_safe_admin_path(next_path))
    _set_admin_session_cookie(response, admin)
    return response


@router.post("/logout")
def logout_from_form() -> RedirectResponse:
    response = _redirect("/admin/login")
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@router.get("/account", response_class=HTMLResponse)
def account_page(request: Request) -> HTMLResponse:
    return _render(
        "admin/account.html",
        request=request,
        active="account",
        error=request.query_params.get("error") or "",
        updated=bool(request.query_params.get("updated")),
    )


@router.post("/account/password")
def update_current_password_from_form(
    request: Request,
    session: SessionDep,
    current_password: PasswordForm,
    new_password: NewPasswordForm,
    confirm_password: NewPasswordForm,
) -> RedirectResponse:
    admin = _current_admin(request)
    managed_admin = session.get(AdminUser, admin.id)
    if managed_admin is None:
        raise HTTPException(status_code=404, detail="管理员不存在")
    if not verify_password(current_password, managed_admin.password_hash):
        return _redirect("/admin/account?error=current_password")
    if len(new_password) < 8:
        return _redirect("/admin/account?error=password_length")
    if new_password != confirm_password:
        return _redirect("/admin/account?error=password_confirm")

    managed_admin.password_hash = hash_password(new_password)
    session.add(managed_admin)
    record_audit_log(
        session,
        actor=managed_admin,
        action="admin.password_update",
        entity_type="admin_user",
        entity_id=managed_admin.email,
        summary=f"{managed_admin.email} 修改了登录密码",
    )
    session.commit()
    response = _redirect("/admin/account?updated=1")
    _set_admin_session_cookie(response, managed_admin)
    return response


@router.get("", response_class=HTMLResponse)
def dashboard(request: Request, session: SessionDep, redis: RedisDep) -> HTMLResponse:
    products = list_active_products(session, limit=8)
    orders = list_recent_orders(session, limit=8)
    low_stock_products = list_low_stock_products(session, limit=10)
    redis_ok = _redis_ok(redis)

    return _render(
        "admin/dashboard.html",
        request=request,
        active="dashboard",
        products=products,
        orders=orders,
        product_count=len(session.exec(select(Product.id)).all()),
        order_count=count_orders(session),
        customer_count=count_customers(session),
        stock_warning_count=len(low_stock_products),
        total_revenue=sum_order_revenue(session),
        status_counts=count_orders_by_status(session),
        low_stock_products=low_stock_products,
        database_ok=True,
        redis_ok=redis_ok,
    )


@router.get("/products", response_class=HTMLResponse)
def product_page(
    request: Request,
    session: SessionDep,
    q: SearchQuery = None,
    category: CategoryQuery = None,
    status: ProductStatusQuery = None,
    low_stock: LowStockQuery = False,
) -> HTMLResponse:
    products = list_products(
        session,
        query=q,
        category=category,
        status=status,
        low_stock=low_stock,
        limit=100,
    )
    return _render(
        "admin/products.html",
        request=request,
        active="products",
        products=products,
        filters={
            "q": q or "",
            "category": category or "",
            "status": status.value if status else "",
            "low_stock": low_stock,
        },
    )


@router.post("/products")
def create_product_from_form(
    request: Request,
    session: SessionDep,
    sku: SkuForm,
    name: NameForm,
    category: CategoryForm,
    price: PriceForm,
    stock_on_hand: StockForm,
    low_stock_threshold: ThresholdForm,
    description: DescriptionForm = "",
    image_url: ImageUrlForm = "",
    status: StatusForm = ProductStatus.ACTIVE,
) -> RedirectResponse:
    try:
        parsed_price = Decimal(price)
    except InvalidOperation as exc:
        raise HTTPException(status_code=400, detail="价格格式不正确") from exc

    product = Product(
        sku=sku.strip(),
        name=name.strip(),
        description=description.strip(),
        image_url=image_url.strip(),
        category=category.strip(),
        price=parsed_price,
        stock_on_hand=stock_on_hand,
        low_stock_threshold=low_stock_threshold,
        status=status,
    )
    session.add(product)
    record_audit_log(
        session,
        actor=_current_admin(request),
        action="product.create",
        entity_type="product",
        entity_id=product.sku,
        summary=f"创建商品 {product.name}（{product.sku}）",
    )
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="商品 SKU 已存在") from exc
    return _redirect("/admin/products?created=1")


@router.get("/products/{sku}/edit", response_class=HTMLResponse)
def edit_product_page(sku: str, request: Request, session: SessionDep) -> HTMLResponse:
    product = get_product_by_sku(session, sku)
    if product is None:
        raise HTTPException(status_code=404, detail="商品不存在")
    return _render(
        "admin/product_edit.html",
        request=request,
        active="products",
        product=product,
        adjustments=list_inventory_adjustments(session, sku=sku, limit=20),
    )


@router.post("/products/{sku}")
def update_product_from_form(
    request: Request,
    sku: str,
    session: SessionDep,
    name: NameForm,
    category: CategoryForm,
    price: PriceForm,
    stock_on_hand: StockForm,
    low_stock_threshold: ThresholdForm,
    description: DescriptionForm = "",
    image_url: ImageUrlForm = "",
    status: StatusForm = ProductStatus.ACTIVE,
) -> RedirectResponse:
    product = get_product_by_sku(session, sku)
    if product is None:
        raise HTTPException(status_code=404, detail="商品不存在")
    try:
        parsed_price = Decimal(price)
    except InvalidOperation as exc:
        raise HTTPException(status_code=400, detail="价格格式不正确") from exc

    product.name = name.strip()
    product.category = category.strip()
    product.price = parsed_price
    product.image_url = image_url.strip()
    product.stock_on_hand = stock_on_hand
    product.low_stock_threshold = low_stock_threshold
    product.description = description.strip()
    product.status = status
    session.add(product)
    record_audit_log(
        session,
        actor=_current_admin(request),
        action="product.update",
        entity_type="product",
        entity_id=product.sku,
        summary=f"更新商品 {product.name}（{product.sku}）",
    )
    session.commit()
    return _redirect("/admin/products?updated=1")


@router.post("/products/{sku}/image")
async def upload_product_image_from_form(
    request: Request,
    sku: str,
    session: SessionDep,
    image: Annotated[UploadFile, File(...)],
) -> RedirectResponse:
    product = get_product_by_sku(session, sku)
    if product is None:
        raise HTTPException(status_code=404, detail="商品不存在")
    settings = get_settings()
    content = await image.read(settings.upload_max_bytes + 1)
    if len(content) > settings.upload_max_bytes:
        raise HTTPException(status_code=413, detail="图片不能超过上传大小限制")
    if image.content_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
        raise HTTPException(status_code=400, detail="仅支持 JPG、PNG、WEBP 或 GIF 图片")

    extension = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }[image.content_type]
    safe_sku = re.sub(r"[^A-Za-z0-9_-]+", "-", sku).strip("-") or "product"
    filename = f"{safe_sku}-{int(datetime.now(UTC).timestamp())}{extension}"
    upload_dir = Path(settings.upload_dir) / "products"
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / filename
    target.write_bytes(content)

    product.image_url = f"/media/products/{filename}"
    product.updated_at = datetime.now(UTC)
    session.add(product)
    record_audit_log(
        session,
        actor=_current_admin(request),
        action="product.image_upload",
        entity_type="product",
        entity_id=product.sku,
        summary=f"上传商品图片 {product.sku}",
    )
    session.commit()
    return _redirect(f"/admin/products/{sku}/edit?image_uploaded=1")


@router.post("/products/{sku}/inventory")
def adjust_product_inventory_from_form(
    request: Request,
    sku: str,
    session: SessionDep,
    change_quantity: InventoryChangeForm,
    reason: ReasonForm,
) -> RedirectResponse:
    product = get_product_by_sku(session, sku)
    if product is None:
        raise HTTPException(status_code=404, detail="商品不存在")
    if not reason.strip():
        raise HTTPException(status_code=400, detail="调整原因不能为空")
    actor = _current_admin(request)
    try:
        adjustment = adjust_inventory(
            session,
            product=product,
            actor=actor,
            change_quantity=change_quantity,
            reason=reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    record_audit_log(
        session,
        actor=actor,
        action="inventory.adjust",
        entity_type="product",
        entity_id=product.sku,
        summary=(
            f"调整库存 {product.sku}：{adjustment.stock_before} -> "
            f"{adjustment.stock_after}，原因：{adjustment.reason}"
        ),
    )
    session.commit()
    return _redirect(f"/admin/products/{sku}/edit?inventory_updated=1")


@router.get("/audit", response_class=HTMLResponse)
def audit_page(request: Request, session: SessionDep) -> HTMLResponse:
    return _render(
        "admin/audit.html",
        request=request,
        active="audit",
        logs=list_audit_logs(session, limit=100),
    )


@router.get("/admins", response_class=HTMLResponse)
def admins_page(request: Request, session: SessionDep) -> HTMLResponse:
    _require_permission(request, AdminPermission.MANAGE_ADMINS)
    return _render(
        "admin/admins.html",
        request=request,
        active="admins",
        admins=list_admins(session, limit=100),
        role_permissions=ROLE_PERMISSIONS,
        all_permissions=list(AdminPermission),
    )


@router.post("/admins")
def create_admin_from_form(
    request: Request,
    session: SessionDep,
    email: EmailForm,
    full_name: NameForm,
    password: PasswordForm,
    role: RoleForm,
) -> RedirectResponse:
    actor = _require_permission(request, AdminPermission.MANAGE_ADMINS)
    normalized_email = email.strip().lower()
    if get_admin_by_email(session, normalized_email) is not None:
        raise HTTPException(status_code=409, detail="管理员邮箱已存在")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="密码至少需要 8 位")

    admin = AdminUser(
        email=normalized_email,
        full_name=full_name.strip(),
        password_hash=hash_password(password),
        role=role,
    )
    session.add(admin)
    record_audit_log(
        session,
        actor=actor,
        action="admin.create",
        entity_type="admin_user",
        entity_id=normalized_email,
        summary=f"创建管理员 {admin.full_name}（{normalized_email}）",
    )
    session.commit()
    return _redirect("/admin/admins?created=1")


@router.post("/admins/{admin_id}/role")
def update_admin_role_from_form(
    request: Request,
    admin_id: UUID,
    session: SessionDep,
    role: RoleForm,
) -> RedirectResponse:
    actor = _require_permission(request, AdminPermission.MANAGE_ADMINS)
    admin = get_admin_by_id(session, admin_id)
    if admin is None:
        raise HTTPException(status_code=404, detail="管理员不存在")
    if admin.id == actor.id and role != AdminRole.OWNER:
        raise HTTPException(status_code=409, detail="不能移除自己的所有者权限")

    admin.role = role
    session.add(admin)
    record_audit_log(
        session,
        actor=actor,
        action="admin.role_update",
        entity_type="admin_user",
        entity_id=admin.email,
        summary=f"调整管理员 {admin.email} 角色为 {role.value}",
    )
    session.commit()
    return _redirect("/admin/admins?role_updated=1")


@router.post("/admins/{admin_id}/status")
def update_admin_status_from_form(
    request: Request,
    admin_id: UUID,
    session: SessionDep,
    action: ActionForm,
) -> RedirectResponse:
    actor = _require_permission(request, AdminPermission.MANAGE_ADMINS)
    admin = get_admin_by_id(session, admin_id)
    if admin is None:
        raise HTTPException(status_code=404, detail="管理员不存在")
    if action not in {"activate", "deactivate"}:
        raise HTTPException(status_code=400, detail="账号操作不正确")
    if admin.id == actor.id and action == "deactivate":
        raise HTTPException(status_code=409, detail="不能停用当前登录账号")

    admin.is_active = action == "activate"
    session.add(admin)
    record_audit_log(
        session,
        actor=actor,
        action=f"admin.{action}",
        entity_type="admin_user",
        entity_id=admin.email,
        summary=f"{'启用' if admin.is_active else '停用'}管理员 {admin.email}",
    )
    session.commit()
    return _redirect("/admin/admins?status_updated=1")


@router.get("/api-keys", response_class=HTMLResponse)
def api_keys_page(request: Request, session: SessionDep) -> HTMLResponse:
    _require_permission(request, AdminPermission.MANAGE_API_KEYS)
    return _render(
        "admin/api_keys.html",
        request=request,
        active="api_keys",
        api_keys=list_api_keys(session, limit=100),
        access_logs=list_api_access_logs(session, limit=100),
        created_key="",
    )


@router.post("/api-keys", response_class=HTMLResponse)
def create_api_key_from_form(
    request: Request,
    session: SessionDep,
    name: NameForm,
) -> HTMLResponse:
    actor = _require_permission(request, AdminPermission.MANAGE_API_KEYS)
    api_key, raw_key = create_api_key(session, name=name, actor=actor)
    record_audit_log(
        session,
        actor=actor,
        action="api_key.create",
        entity_type="api_key",
        entity_id=api_key.key_prefix,
        summary=f"创建 API Key {api_key.name}（{api_key.key_prefix}）",
    )
    session.commit()
    return _render(
        "admin/api_keys.html",
        request=request,
        active="api_keys",
        api_keys=list_api_keys(session, limit=100),
        access_logs=list_api_access_logs(session, limit=100),
        created_key=raw_key,
    )


@router.post("/api-keys/{api_key_id}/status")
def update_api_key_status_from_form(
    request: Request,
    api_key_id: UUID,
    session: SessionDep,
    action: ActionForm,
) -> RedirectResponse:
    actor = _require_permission(request, AdminPermission.MANAGE_API_KEYS)
    api_key = get_api_key_by_id(session, api_key_id)
    if api_key is None:
        raise HTTPException(status_code=404, detail="API Key 不存在")
    if action not in {"activate", "deactivate"}:
        raise HTTPException(status_code=400, detail="API Key 操作不正确")

    api_key.is_active = action == "activate"
    session.add(api_key)
    record_audit_log(
        session,
        actor=actor,
        action=f"api_key.{action}",
        entity_type="api_key",
        entity_id=api_key.key_prefix,
        summary=f"{'启用' if api_key.is_active else '停用'} API Key {api_key.name}",
    )
    session.commit()
    return _redirect("/admin/api-keys?status_updated=1")


@router.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request, session: SessionDep) -> HTMLResponse:
    return _render(
        "admin/reports.html",
        request=request,
        active="reports",
        total_revenue=sum_order_revenue(session),
        order_count=count_orders(session),
        customer_count=count_customers(session),
        low_stock_count=len(list_low_stock_products(session, limit=1000)),
        status_counts=count_orders_by_status(session),
        payment_count=len(session.exec(select(Payment.id)).all()),
        refund_count=len(
            session.exec(select(Payment.id).where(Payment.status == PaymentStatus.REFUNDED)).all()
        ),
        return_count=len(session.exec(select(ReturnRequest.id)).all()),
        api_access_count=len(session.exec(select(ApiAccessLog.id)).all()),
    )


@router.get("/reports/export")
def export_reports(session: SessionDep) -> Response:
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["指标", "数值"])
    writer.writerow(["累计销售额", sum_order_revenue(session)])
    writer.writerow(["订单数", count_orders(session)])
    writer.writerow(["客户数", count_customers(session)])
    writer.writerow(["低库存商品数", len(list_low_stock_products(session, limit=1000))])
    writer.writerow(["支付记录数", len(session.exec(select(Payment.id)).all())])
    refund_count = len(
        session.exec(select(Payment.id).where(Payment.status == PaymentStatus.REFUNDED)).all()
    )
    writer.writerow(["退款记录数", refund_count])
    writer.writerow(["售后申请数", len(session.exec(select(ReturnRequest.id)).all())])
    writer.writerow(["API 访问记录数", len(session.exec(select(ApiAccessLog.id)).all())])
    response = Response("\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = 'attachment; filename="commerce-report.csv"'
    return response


@router.get("/orders", response_class=HTMLResponse)
def orders_page(
    request: Request,
    session: SessionDep,
    q: SearchQuery = None,
    status: OrderStatusQuery = None,
    created_from: DateQuery = None,
    created_to: DateQuery = None,
) -> HTMLResponse:
    start_at = _parse_date_start(created_from)
    end_at = _parse_date_end(created_to)
    order_rows = list_order_summaries(
        session,
        query=q,
        status=status,
        created_from=start_at,
        created_to=end_at,
        limit=100,
    )
    next_statuses_by_order = {
        row.order.id: sorted(
            ALLOWED_ORDER_TRANSITIONS[row.order.status],
            key=lambda next_status: next_status.value,
        )
        for row in order_rows
    }
    return _render(
        "admin/orders.html",
        request=request,
        active="orders",
        order_rows=order_rows,
        next_statuses_by_order=next_statuses_by_order,
        return_to=_request_path_with_query(request),
        export_path=_admin_path_with_query("/admin/orders/export", request.url.query),
        filters={
            "q": q or "",
            "status": status.value if status else "",
            "created_from": created_from or "",
            "created_to": created_to or "",
        },
    )


@router.get("/orders/export")
def export_orders(
    session: SessionDep,
    q: SearchQuery = None,
    status: OrderStatusQuery = None,
    created_from: DateQuery = None,
    created_to: DateQuery = None,
) -> Response:
    order_rows = list_order_summaries(
        session,
        query=q,
        status=status,
        created_from=_parse_date_start(created_from),
        created_to=_parse_date_end(created_to),
        limit=10_000,
    )
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "订单号",
            "客户姓名",
            "客户邮箱",
            "状态",
            "金额",
            "币种",
            "承运商",
            "物流单号",
            "备注",
            "创建时间",
        ]
    )
    for row in order_rows:
        writer.writerow(
            [
                row.order.id,
                row.customer.full_name,
                row.customer.email,
                templates.filters["order_status_label"](row.order.status),
                row.order.total_amount,
                row.order.currency,
                row.order.shipping_carrier,
                row.order.tracking_number,
                row.order.note,
                row.order.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            ]
        )
    response = Response("\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = 'attachment; filename="orders.csv"'
    return response


@router.get("/customers", response_class=HTMLResponse)
def customers_page(
    request: Request,
    session: SessionDep,
    q: SearchQuery = None,
) -> HTMLResponse:
    customers = list_customer_summaries(session, query=q, limit=100)
    return _render(
        "admin/customers.html",
        request=request,
        active="customers",
        customers=customers,
        filters={"q": q or ""},
    )


@router.get("/customers/{customer_id}", response_class=HTMLResponse)
def customer_detail(customer_id: UUID, request: Request, session: SessionDep) -> HTMLResponse:
    customer = session.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="客户不存在")
    orders = list_orders_for_customer(session, customer_id, limit=100)
    total_spent = sum((order.total_amount for order in orders), Decimal("0.00"))
    return _render(
        "admin/customer_detail.html",
        request=request,
        active="customers",
        customer=customer,
        orders=orders,
        total_spent=total_spent,
    )


@router.get("/orders/{order_id}", response_class=HTMLResponse)
def order_detail(order_id: UUID, request: Request, session: SessionDep) -> HTMLResponse:
    order = get_order(session, order_id)
    next_statuses = sorted(
        ALLOWED_ORDER_TRANSITIONS[order.status],
        key=lambda status: status.value,
    )
    return _render(
        "admin/order_detail.html",
        request=request,
        active="orders",
        order=order,
        next_statuses=next_statuses,
        payments=list_payments_for_order(session, order_id),
        returns=list_returns_for_order(session, order_id),
        shipments=list_shipments_for_order(session, order_id),
    )


@router.post("/orders/{order_id}/returns")
def create_return_from_form(
    request: Request,
    order_id: UUID,
    session: SessionDep,
    reason: ReasonForm,
) -> RedirectResponse:
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    actor = _current_admin(request)
    return_request = ReturnRequest(
        order_id=order.id,
        reason=reason.strip(),
        created_by_id=actor.id,
        created_by_email=actor.email,
    )
    session.add(return_request)
    record_audit_log(
        session,
        actor=actor,
        action="return.create",
        entity_type="order",
        entity_id=order.id,
        summary=f"创建售后申请：{return_request.reason}",
    )
    session.commit()
    return _redirect(f"/admin/orders/{order_id}?return_created=1")


@router.post("/orders/{order_id}/returns/{return_id}/status")
def update_return_status_from_form(
    request: Request,
    order_id: UUID,
    return_id: UUID,
    session: SessionDep,
    status: Annotated[ReturnStatus, Form(...)],
    resolution_note: OptionalTextForm = "",
) -> RedirectResponse:
    return_request = session.get(ReturnRequest, return_id)
    if return_request is None or return_request.order_id != order_id:
        raise HTTPException(status_code=404, detail="售后申请不存在")
    return_request.status = status
    return_request.resolution_note = resolution_note.strip()
    return_request.updated_at = datetime.now(UTC)
    session.add(return_request)
    if status == ReturnStatus.COMPLETED:
        for payment in list_payments_for_order(session, order_id):
            if payment.status == PaymentStatus.SUCCEEDED:
                managed_payment = session.get(Payment, payment.id)
                if managed_payment is not None:
                    managed_payment.status = PaymentStatus.REFUNDED
                    session.add(managed_payment)
    record_audit_log(
        session,
        actor=_current_admin(request),
        action="return.status_update",
        entity_type="return_request",
        entity_id=return_request.id,
        summary=f"售后申请状态更新为 {status.value}",
    )
    session.commit()
    return _redirect(f"/admin/orders/{order_id}?return_updated=1")


@router.post("/orders/{order_id}/payments/mock")
def create_mock_payment_from_form(
    request: Request,
    order_id: UUID,
    session: SessionDep,
) -> RedirectResponse:
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    try:
        payment = simulate_payment(session, order)
    except PaymentNotAllowedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    record_audit_log(
        session,
        actor=_current_admin(request),
        action="payment.mock_succeeded",
        entity_type="order",
        entity_id=order.id,
        summary=f"模拟支付成功，支付流水 {payment.reference}",
    )
    session.commit()
    return _redirect(f"/admin/orders/{order_id}?paid=1")


@router.post("/orders/{order_id}/status")
def update_order_status_from_form(
    request: Request,
    order_id: UUID,
    session: SessionDep,
    status: OrderStatusForm,
    return_to: Annotated[str, Form()] = "",
    shipping_carrier: OptionalTextForm = "",
    tracking_number: OptionalTextForm = "",
) -> RedirectResponse:
    try:
        order = update_order_status(session, order_id, status)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidOrderTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    managed_order = session.get(Order, order_id)
    if managed_order is not None and status == OrderStatus.FULFILLED:
        if shipping_carrier.strip():
            managed_order.shipping_carrier = shipping_carrier.strip()
        if tracking_number.strip():
            managed_order.tracking_number = tracking_number.strip()
        upsert_shipment(
            session,
            order=managed_order,
            carrier=managed_order.shipping_carrier,
            tracking_number=managed_order.tracking_number,
        )
        managed_order.shipped_at = datetime.now(UTC)
        session.add(managed_order)
    record_audit_log(
        session,
        actor=_current_admin(request),
        action="order.status_update",
        entity_type="order",
        entity_id=order.id,
        summary=f"订单 {order.id} 状态更新为 {status.value}",
    )
    session.commit()
    redirect_path = (
        _safe_admin_path(return_to)
        if return_to
        else f"/admin/orders/{order_id}?updated=1"
    )
    return _redirect(redirect_path)


@router.post("/orders/{order_id}/fulfillment")
def update_order_fulfillment_from_form(
    request: Request,
    order_id: UUID,
    session: SessionDep,
    note: OptionalTextForm = "",
    shipping_carrier: OptionalTextForm = "",
    tracking_number: OptionalTextForm = "",
) -> RedirectResponse:
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")

    order.note = note.strip()
    order.shipping_carrier = shipping_carrier.strip()
    order.tracking_number = tracking_number.strip()
    if order.shipping_carrier or order.tracking_number:
        order.shipped_at = order.shipped_at or datetime.now(UTC)
        upsert_shipment(
            session,
            order=order,
            carrier=order.shipping_carrier,
            tracking_number=order.tracking_number,
        )
    session.add(order)
    record_audit_log(
        session,
        actor=_current_admin(request),
        action="order.fulfillment_update",
        entity_type="order",
        entity_id=order.id,
        summary=f"更新订单 {order.id} 的备注和物流信息",
    )
    session.commit()
    return _redirect(f"/admin/orders/{order_id}?fulfillment_updated=1")


@router.get("/sandbox", response_class=HTMLResponse)
def sandbox_page(request: Request, session: SessionDep, redis: RedisDep) -> HTMLResponse:
    products = list_active_products(session, limit=100)
    cart = None
    customer = None
    email = request.query_params.get("email")
    if email:
        customer = get_customer_by_email(session, email)
        if customer is not None:
            try:
                cart = read_cart(session, redis, customer.id)
            except CartNotAvailableError:
                cart = None
    return _render(
        "admin/sandbox.html",
        request=request,
        active="sandbox",
        products=products,
        customer=customer,
        cart=cart,
    )


@router.post("/sandbox/customers")
def create_customer_from_form(
    request: Request,
    session: SessionDep,
    email: EmailForm,
    full_name: NameForm,
) -> RedirectResponse:
    normalized_email = email.strip().lower()
    customer = get_customer_by_email(session, normalized_email)
    if customer is None:
        customer = Customer(email=normalized_email, full_name=full_name.strip())
        session.add(customer)
        record_audit_log(
            session,
            actor=_current_admin(request),
            action="customer.create",
            entity_type="customer",
            entity_id=normalized_email,
            summary=f"创建客户 {customer.full_name}（{normalized_email}）",
        )
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail="客户邮箱已存在") from exc
    return _redirect(f"/admin/sandbox?email={normalized_email}")


@router.post("/sandbox/cart")
def add_cart_item_from_form(
    request: Request,
    session: SessionDep,
    redis: RedisDep,
    customer_id: CustomerIdForm,
    sku: SkuForm,
    quantity: QuantityForm,
) -> RedirectResponse:
    customer = session.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="客户不存在")
    try:
        add_item(session, redis, customer_id, CartItemWrite(sku=sku, quantity=quantity))
    except ProductUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CartNotAvailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    record_audit_log(
        session,
        actor=_current_admin(request),
        action="cart.add_item",
        entity_type="customer",
        entity_id=customer_id,
        summary=f"为客户 {customer.email} 加购 {sku} x {quantity}",
    )
    session.commit()
    return _redirect(f"/admin/sandbox?email={customer.email}")


@router.post("/sandbox/checkout")
def checkout_from_form(
    request: Request,
    session: SessionDep,
    redis: RedisDep,
    customer_id: CustomerIdForm,
) -> RedirectResponse:
    try:
        order = checkout(session, redis, customer_id)
    except (CustomerNotFoundError, EmptyCartError, ProductUnavailableError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CartNotAvailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    record_audit_log(
        session,
        actor=_current_admin(request),
        action="order.checkout",
        entity_type="order",
        entity_id=order.id,
        summary=f"创建测试订单 {order.id}",
    )
    session.commit()
    return _redirect(f"/admin/orders/{order.id}")


def _render(template_name: str, **context: object) -> HTMLResponse:
    request = context.get("request")
    if isinstance(request, Request) and "current_admin" not in context:
        context["current_admin"] = getattr(request.state, "admin", None)
    template = templates.get_template(template_name)
    return HTMLResponse(template.render(**context))


def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


def _redis_ok(redis: RedisDep) -> bool:
    try:
        return bool(redis.ping())
    except Exception:
        return False


def _status_value(status: object) -> str:
    value = getattr(status, "value", status)
    return str(value).lower()


def _parse_date_start(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="开始日期格式不正确") from exc
    return datetime.combine(parsed, time.min, tzinfo=UTC)


def _parse_date_end(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="结束日期格式不正确") from exc
    return datetime.combine(parsed, time.max, tzinfo=UTC)


def _current_admin(request: Request) -> AdminUser:
    admin = getattr(request.state, "admin", None)
    if not isinstance(admin, AdminUser):
        raise HTTPException(status_code=401, detail="请先登录后台")
    return admin


def _set_admin_session_cookie(response: RedirectResponse, admin: AdminUser) -> None:
    settings = get_settings()
    samesite = cast(Literal["lax", "strict", "none"], settings.admin_cookie_samesite)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        create_session_cookie(admin),
        httponly=True,
        secure=settings.admin_cookie_secure,
        samesite=samesite,
        max_age=settings.admin_session_ttl_seconds,
    )


def _require_owner(request: Request) -> AdminUser:
    return _require_permission(request, AdminPermission.MANAGE_ADMINS)


def _require_permission(request: Request, permission: AdminPermission) -> AdminUser:
    admin = _current_admin(request)
    if not admin_has_permission(admin, permission):
        raise HTTPException(status_code=403, detail=f"缺少后台权限：{permission.value}")
    return admin


def _safe_admin_path(path: str) -> str:
    if not path.startswith("/admin") or path.startswith("//"):
        return "/admin"
    if path == "/admin/login":
        return "/admin"
    return path


def _request_path_with_query(request: Request) -> str:
    query = request.url.query
    if not query:
        return request.url.path
    return f"{request.url.path}?{query}"


def _admin_path_with_query(path: str, query: str) -> str:
    if not query:
        return path
    return f"{path}?{query}"
