from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient


def test_admin_dashboard_loads_in_chinese(client: TestClient) -> None:
    response = client.get("/admin")

    assert response.status_code == 200
    assert "电商运营后台" in response.text
    assert "运营概览与系统状态" in response.text
    assert "累计销售额" in response.text
    assert "订单状态分布" in response.text
    assert "低库存商品" in response.text


def test_admin_logout_requires_login(client: TestClient) -> None:
    logout = client.post("/admin/logout", follow_redirects=False)
    assert logout.status_code == 303

    response = client.get("/admin", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/admin/login")


def test_login_failure_is_audited(client: TestClient) -> None:
    client.post("/admin/logout", follow_redirects=False)
    failed = client.post(
        "/admin/login",
        data={"email": "admin@example.com", "password": "wrong-password"},
        follow_redirects=False,
    )
    assert failed.status_code == 303

    client.post(
        "/admin/login",
        data={"email": "admin@example.com", "password": "Admin@123456"},
        follow_redirects=False,
    )
    audit_page = client.get("/admin/audit")
    assert "admin.login_failed" in audit_page.text


def test_current_admin_can_change_password(client: TestClient) -> None:
    page = client.get("/admin/account")
    assert page.status_code == 200
    assert "账号安全" in page.text

    mismatch = client.post(
        "/admin/account/password",
        data={
            "current_password": "bad-current",
            "new_password": "NewAdmin@123",
            "confirm_password": "NewAdmin@123",
        },
        follow_redirects=True,
    )
    assert "当前密码不正确" in mismatch.text

    update = client.post(
        "/admin/account/password",
        data={
            "current_password": "Admin@123456",
            "new_password": "NewAdmin@123",
            "confirm_password": "NewAdmin@123",
        },
        follow_redirects=True,
    )
    assert update.status_code == 200
    assert "密码已更新" in update.text

    client.post("/admin/logout", follow_redirects=False)
    old_login = client.post(
        "/admin/login",
        data={"email": "admin@example.com", "password": "Admin@123456"},
        follow_redirects=False,
    )
    assert old_login.headers["location"] == "/admin/login?error=1"

    new_login = client.post(
        "/admin/login",
        data={"email": "admin@example.com", "password": "NewAdmin@123"},
        follow_redirects=False,
    )
    assert new_login.status_code == 303
    assert new_login.headers["location"] == "/admin"


def test_admin_owner_can_manage_admin_users(client: TestClient) -> None:
    page = client.get("/admin/admins")
    assert page.status_code == 200
    assert "管理员管理" in page.text
    assert "admin@example.com" in page.text

    create_response = client.post(
        "/admin/admins",
        data={
            "email": "operator@example.com",
            "full_name": "运营同事",
            "password": "Operator@123",
            "role": "operator",
        },
        follow_redirects=False,
    )
    assert create_response.status_code == 303

    admins_page = client.get("/admin/admins")
    assert "operator@example.com" in admins_page.text
    assert "运营员" in admins_page.text

    admin_id = _extract_admin_id_for_email(admins_page.text, "operator@example.com")
    role_response = client.post(
        f"/admin/admins/{admin_id}/role",
        data={"role": "owner"},
        follow_redirects=False,
    )
    assert role_response.status_code == 303

    status_response = client.post(
        f"/admin/admins/{admin_id}/status",
        data={"action": "deactivate"},
        follow_redirects=False,
    )
    assert status_response.status_code == 303

    updated_page = client.get("/admin/admins")
    assert "停用" in updated_page.text

    audit_page = client.get("/admin/audit")
    assert "admin.create" in audit_page.text
    assert "admin.role_update" in audit_page.text
    assert "admin.deactivate" in audit_page.text


def test_admin_owner_can_manage_api_keys(client: TestClient) -> None:
    page = client.get("/admin/api-keys")
    assert page.status_code == 200
    assert "API Key 管理" in page.text

    create_response = client.post(
        "/admin/api-keys",
        data={"name": "测试外部系统"},
    )
    assert create_response.status_code == 200
    assert "新 API Key" in create_response.text
    assert "ck_live_" in create_response.text
    assert "测试外部系统" in create_response.text

    api_key_id = _extract_api_key_id_for_name(create_response.text, "测试外部系统")
    status_response = client.post(
        f"/admin/api-keys/{api_key_id}/status",
        data={"action": "deactivate"},
        follow_redirects=False,
    )
    assert status_response.status_code == 303

    updated_page = client.get("/admin/api-keys")
    assert "停用" in updated_page.text

    audit_page = client.get("/admin/audit")
    assert "api_key.create" in audit_page.text
    assert "api_key.deactivate" in audit_page.text


def test_reports_page_and_export(client: TestClient) -> None:
    page = client.get("/admin/reports")
    assert page.status_code == 200
    assert "报表中心" in page.text
    assert "累计销售额" in page.text
    assert "API 访问" in page.text

    export = client.get("/admin/reports/export")
    assert export.status_code == 200
    exported = export.content.decode("utf-8-sig")
    assert "指标,数值" in exported
    assert "订单数" in exported


def test_operator_cannot_manage_admin_users(client: TestClient) -> None:
    client.post(
        "/admin/admins",
        data={
            "email": "limited@example.com",
            "full_name": "普通运营",
            "password": "Limited@123",
            "role": "operator",
        },
        follow_redirects=False,
    )
    client.post("/admin/logout", follow_redirects=False)
    client.post(
        "/admin/login",
        data={"email": "limited@example.com", "password": "Limited@123"},
        follow_redirects=False,
    )

    response = client.get("/admin/admins")
    assert response.status_code == 403
    assert "权限不足" in response.text
    assert "缺少后台权限" in response.text


def test_admin_error_page_is_chinese(client: TestClient) -> None:
    response = client.get("/admin/products/UNKNOWN-SKU/edit")

    assert response.status_code == 404
    assert "页面未找到" in response.text
    assert "商品不存在" in response.text
    assert "返回后台首页" in response.text


def test_admin_product_creation_page_flow(client: TestClient) -> None:
    response = client.post(
        "/admin/products",
        data={
            "sku": "ADMIN-SKU-001",
            "name": "中文测试商品",
            "category": "测试分类",
            "price": "88.00",
            "stock_on_hand": "12",
            "low_stock_threshold": "10",
            "description": "后台创建的商品",
            "status": "active",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303

    page = client.get("/admin/products")
    assert page.status_code == 200
    assert "中文测试商品" in page.text
    assert "商品管理" in page.text

    edit_page = client.get("/admin/products/ADMIN-SKU-001/edit")
    assert edit_page.status_code == 200
    assert "编辑商品" in edit_page.text

    update_response = client.post(
        "/admin/products/ADMIN-SKU-001",
        data={
            "name": "已编辑中文商品",
            "category": "调整分类",
            "price": "99.50",
            "stock_on_hand": "7",
            "low_stock_threshold": "9",
            "description": "更新后的商品描述",
            "status": "draft",
        },
        follow_redirects=False,
    )
    assert update_response.status_code == 303

    updated_page = client.get("/admin/products")
    assert "已编辑中文商品" in updated_page.text
    assert "99.50" in updated_page.text
    assert "7 / 9" in updated_page.text
    assert "草稿" in updated_page.text

    filtered_page = client.get("/admin/products?q=已编辑&status=draft&low_stock=true")
    assert filtered_page.status_code == 200
    assert "已编辑中文商品" in filtered_page.text
    assert "中文测试商品" not in filtered_page.text

    inventory_response = client.post(
        "/admin/products/ADMIN-SKU-001/inventory",
        data={"change_quantity": "5", "reason": "测试入库"},
        follow_redirects=True,
    )
    assert inventory_response.status_code == 200
    assert "库存调整记录" in inventory_response.text
    assert "测试入库" in inventory_response.text
    assert "12" in inventory_response.text

    dashboard = client.get("/admin")
    assert "查看低库存" in dashboard.text

    audit_page = client.get("/admin/audit")
    assert audit_page.status_code == 200
    assert "审计日志" in audit_page.text
    assert "product.create" in audit_page.text
    assert "product.update" in audit_page.text


def test_admin_can_upload_product_image(client: TestClient) -> None:
    create_response = client.post(
        "/admin/products",
        data={
            "sku": "IMAGE-SKU-001",
            "name": "带图商品",
            "category": "images",
            "price": "29.90",
            "stock_on_hand": "5",
            "low_stock_threshold": "1",
            "description": "",
            "status": "active",
        },
        follow_redirects=False,
    )
    assert create_response.status_code == 303

    upload_response = client.post(
        "/admin/products/IMAGE-SKU-001/image",
        files={"image": ("product.png", b"\x89PNG\r\n\x1a\n", "image/png")},
        follow_redirects=True,
    )

    assert upload_response.status_code == 200
    assert "/media/products/IMAGE-SKU-001-" in upload_response.text


def test_admin_sandbox_checkout_flow(client: TestClient) -> None:
    product_response = client.post(
        "/api/v1/products",
        json={
            "sku": "FLOW-SKU-001",
            "name": "流程测试商品",
            "description": "用于中文后台下单",
            "category": "flow",
            "price": "66.00",
            "stock_on_hand": 3,
            "status": "active",
        },
    )
    assert product_response.status_code == 201

    customer_response = client.post(
        "/admin/sandbox/customers",
        data={"email": "flow@example.com", "full_name": "流程买家"},
        follow_redirects=False,
    )
    assert customer_response.status_code == 303

    sandbox = client.get("/admin/sandbox?email=flow@example.com")
    assert "流程买家" in sandbox.text

    customer_id = _extract_hidden_value(sandbox.text, "customer_id")
    cart_response = client.post(
        "/admin/sandbox/cart",
        data={"customer_id": customer_id, "sku": "FLOW-SKU-001", "quantity": "2"},
        follow_redirects=False,
    )
    assert cart_response.status_code == 303

    cart_page = client.get("/admin/sandbox?email=flow@example.com")
    assert "当前购物车" in cart_page.text
    assert "132.00" in cart_page.text

    checkout_response = client.post(
        "/admin/sandbox/checkout",
        data={"customer_id": customer_id},
        follow_redirects=True,
    )
    assert checkout_response.status_code == 200
    assert "订单详情" in checkout_response.text
    assert "流程测试商品" in checkout_response.text
    assert Decimal("132.00") == Decimal(_extract_text_after(checkout_response.text, "订单金额"))
    assert "备注与物流" in checkout_response.text

    order_id = str(checkout_response.url).rstrip("/").rsplit("/", 1)[-1]
    assert "模拟支付成功" in checkout_response.text

    paid_response = client.post(
        f"/admin/orders/{order_id}/payments/mock",
        follow_redirects=True,
    )
    assert paid_response.status_code == 200
    assert "已支付" in paid_response.text
    assert "标记为已履约" in paid_response.text
    assert "支付记录" in paid_response.text
    assert "MOCK-" in paid_response.text
    assert "售后申请" in paid_response.text

    return_response = client.post(
        f"/admin/orders/{order_id}/returns",
        data={"reason": "客户申请退货"},
        follow_redirects=True,
    )
    assert return_response.status_code == 200
    assert "客户申请退货" in return_response.text
    assert "待处理" in return_response.text

    return_id = _extract_return_id_for_reason(return_response.text, "客户申请退货")
    completed_return = client.post(
        f"/admin/orders/{order_id}/returns/{return_id}/status",
        data={"status": "completed", "resolution_note": "已完成退款"},
        follow_redirects=True,
    )
    assert completed_return.status_code == 200
    assert "已退款" in completed_return.text
    assert "已完成" in completed_return.text

    fulfillment_response = client.post(
        f"/admin/orders/{order_id}/fulfillment",
        data={
            "note": "优先发货",
            "shipping_carrier": "顺丰速运",
            "tracking_number": "SF123456789",
        },
        follow_redirects=True,
    )
    assert fulfillment_response.status_code == 200
    assert "优先发货" in fulfillment_response.text
    assert "SF123456789" in fulfillment_response.text

    fulfilled_response = client.post(
        f"/admin/orders/{order_id}/status",
        data={"status": "fulfilled"},
        follow_redirects=True,
    )
    assert fulfilled_response.status_code == 200
    assert "已履约" in fulfilled_response.text
    assert "当前订单状态不可继续流转" in fulfilled_response.text

    today = datetime.now(UTC).date().isoformat()
    filtered_orders = client.get(
        f"/admin/orders?q=flow@example.com&status=fulfilled&created_from={today}&created_to={today}"
    )
    assert filtered_orders.status_code == 200
    assert order_id in filtered_orders.text
    assert "流程买家" in filtered_orders.text
    assert "flow@example.com" in filtered_orders.text
    assert "已履约" in filtered_orders.text
    assert "无需处理" in filtered_orders.text
    assert "顺丰速运" in filtered_orders.text
    assert "导出 CSV" in filtered_orders.text

    export_response = client.get(
        f"/admin/orders/export?q=flow@example.com&status=fulfilled&created_from={today}"
        f"&created_to={today}"
    )
    assert export_response.status_code == 200
    assert export_response.headers["content-type"].startswith("text/csv")
    exported = export_response.content.decode("utf-8-sig")
    assert "订单号,客户姓名,客户邮箱,状态,金额,币种,承运商,物流单号,备注,创建时间" in exported
    assert order_id in exported
    assert "流程买家" in exported
    assert "flow@example.com" in exported
    assert "SF123456789" in exported

    customers_page = client.get("/admin/customers")
    assert customers_page.status_code == 200
    assert "客户管理" in customers_page.text
    assert "流程买家" in customers_page.text
    assert "132.00" in customers_page.text

    customer_page = client.get(f"/admin/customers/{customer_id}")
    assert customer_page.status_code == 200
    assert "客户详情" in customer_page.text
    assert "历史订单" in customer_page.text
    assert order_id in customer_page.text
    assert "已履约" in customer_page.text

    filtered_customers = client.get("/admin/customers?q=flow@example.com")
    assert filtered_customers.status_code == 200
    assert "流程买家" in filtered_customers.text
    assert "flow@example.com" in filtered_customers.text


def _extract_hidden_value(html: str, name: str) -> str:
    marker = f'name="{name}" value="'
    start = html.index(marker) + len(marker)
    end = html.index('"', start)
    return html[start:end]


def _extract_text_after(html: str, label: str) -> str:
    start = html.index(label)
    value_start = html.index("<td>", start) + len("<td>")
    value_end = html.index(" ", value_start)
    return html[value_start:value_end]


def _extract_admin_id_for_email(html: str, email: str) -> str:
    row_start = html.rfind("<tr>", 0, html.index(email))
    marker = "/admin/admins/"
    start = html.index(marker, row_start) + len(marker)
    end = html.index("/", start)
    return html[start:end]


def _extract_api_key_id_for_name(html: str, name: str) -> str:
    row_start = html.rfind("<tr>", 0, html.index(name))
    marker = "/admin/api-keys/"
    start = html.index(marker, row_start) + len(marker)
    end = html.index("/", start)
    return html[start:end]


def _extract_return_id_for_reason(html: str, reason: str) -> str:
    row_start = html.rfind("<tr>", 0, html.index(reason))
    marker = "/returns/"
    start = html.index(marker, row_start) + len(marker)
    end = html.index("/status", start)
    return html[start:end]
