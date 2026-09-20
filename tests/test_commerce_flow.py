import hashlib
import hmac
import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from commerce.core.config import get_settings


def test_api_requires_api_key(client: TestClient) -> None:
    response = client.get("/api/v1/products", headers={"X-API-Key": ""})
    assert response.status_code == 401


def test_api_error_responses_stay_json(client: TestClient) -> None:
    response = client.get("/api/v1/products/UNKNOWN-SKU")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Product not found."}


def test_api_key_can_be_created_and_deactivated(client: TestClient) -> None:
    create_response = client.post("/admin/api-keys", data={"name": "集成测试 Key"})
    raw_key = _extract_input_value_after(create_response.text, "新 API Key")

    ok_response = client.get("/api/v1/products", headers={"X-API-Key": raw_key})
    assert ok_response.status_code == 200

    api_key_id = _extract_api_key_id_for_name(create_response.text, "集成测试 Key")
    client.post(
        f"/admin/api-keys/{api_key_id}/status",
        data={"action": "deactivate"},
        follow_redirects=False,
    )

    blocked_response = client.get("/api/v1/products", headers={"X-API-Key": raw_key})
    assert blocked_response.status_code == 401


def test_api_access_is_logged(client: TestClient) -> None:
    response = client.get("/api/v1/products")
    assert response.status_code == 200

    page = client.get("/admin/api-keys")
    assert "最近 API 访问" in page.text
    assert "/api/v1/products" in page.text
    assert "accepted" in page.text


def test_api_rate_limit(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "api_rate_limit_requests", 1)
    monkeypatch.setattr(settings, "api_rate_limit_window_seconds", 60)

    first = client.get("/api/v1/products")
    second = client.get("/api/v1/products")

    assert first.status_code == 200
    assert second.status_code == 429


def test_ops_status_and_metrics(client: TestClient) -> None:
    status_response = client.get("/ops/status")
    metrics_response = client.get("/ops/metrics")

    assert status_response.status_code == 200
    assert status_response.json()["status"] == "ok"
    assert metrics_response.status_code == 200
    assert "commerce_requests_total" in metrics_response.text


def test_customer_cart_checkout_flow(client: TestClient) -> None:
    customer_response = client.post(
        "/api/v1/customers",
        json={"email": "ada@example.com", "full_name": "Ada Lovelace"},
    )
    assert customer_response.status_code == 201
    customer_id = customer_response.json()["id"]

    product_response = client.post(
        "/api/v1/products",
        json={
            "sku": "SKU-001",
            "name": "Focus Desk Lamp",
            "description": "A clean lamp for late-night build sessions.",
            "category": "workspace",
            "price": "129.00",
            "stock_on_hand": 8,
            "status": "active",
        },
    )
    assert product_response.status_code == 201

    cart_response = client.post(
        f"/api/v1/cart/{customer_id}/items",
        json={"sku": "SKU-001", "quantity": 2},
    )
    assert cart_response.status_code == 200
    assert cart_response.json()["total_amount"] == "258.00"

    order_response = client.post("/api/v1/orders/checkout", json={"customer_id": customer_id})
    assert order_response.status_code == 201
    order = order_response.json()
    assert order["status"] == "created"
    assert Decimal(order["total_amount"]) == Decimal("258.00")
    assert order["lines"][0]["sku"] == "SKU-001"

    product_after = client.get("/api/v1/products/SKU-001").json()
    assert product_after["stock_on_hand"] == 6


def test_storefront_checkout_flow(client: TestClient) -> None:
    product_response = client.post(
        "/api/v1/products",
        json={
            "sku": "STORE-SKU",
            "name": "前台商品",
            "description": "前台商城可购买商品",
            "category": "store",
            "price": "39.00",
            "stock_on_hand": 4,
            "status": "active",
        },
    )
    assert product_response.status_code == 201

    store_page = client.get("/store")
    assert store_page.status_code == 200
    assert "中文电商商城" in store_page.text
    assert "前台商品" in store_page.text

    customer_response = client.post(
        "/store/customers",
        data={"email": "store@example.com", "full_name": "前台买家"},
        follow_redirects=False,
    )
    assert customer_response.status_code == 303

    loaded_store = client.get("/store?email=store@example.com")
    customer_id = _extract_hidden_value(loaded_store.text, "customer_id")
    cart_response = client.post(
        "/store/cart",
        data={
            "customer_id": customer_id,
            "email": "store@example.com",
            "sku": "STORE-SKU",
            "quantity": "2",
        },
        follow_redirects=True,
    )
    assert "合计 78.00 CNY" in cart_response.text

    checkout_response = client.post(
        "/store/checkout",
        data={"customer_id": customer_id, "email": "store@example.com"},
        follow_redirects=True,
    )
    assert checkout_response.status_code == 200
    assert "订单已创建" in checkout_response.text
    assert "前台商品" in checkout_response.text


def test_payment_checkout_and_signed_webhook(client: TestClient) -> None:
    customer_response = client.post(
        "/api/v1/customers",
        json={"email": "pay@example.com", "full_name": "Pay Buyer"},
    )
    customer_id = customer_response.json()["id"]
    client.post(
        "/api/v1/products",
        json={
            "sku": "PAY-SKU",
            "name": "Payment Item",
            "description": "",
            "category": "pay",
            "price": "50.00",
            "stock_on_hand": 2,
            "status": "active",
        },
    )
    client.post(f"/api/v1/cart/{customer_id}/items", json={"sku": "PAY-SKU", "quantity": 1})
    order_response = client.post("/api/v1/orders/checkout", json={"customer_id": customer_id})
    order_id = order_response.json()["id"]

    checkout_response = client.post(f"/api/v1/payments/orders/{order_id}/checkout")
    assert checkout_response.status_code == 201
    payment = checkout_response.json()
    assert payment["status"] == "pending"
    assert payment["checkout_url"]

    payload = {
        "event_id": "evt_test_payment_success",
        "event_type": "payment.succeeded",
        "reference": payment["reference"],
        "status": "succeeded",
    }
    body = json.dumps(payload).encode("utf-8")
    signature = hmac.new(
        b"local-webhook-secret-change-me",
        body,
        hashlib.sha256,
    ).hexdigest()
    webhook_response = client.post(
        "/api/v1/payments/webhooks/mock",
        content=body,
        headers={"X-Commerce-Signature": signature, "Content-Type": "application/json"},
    )
    assert webhook_response.status_code == 200
    assert webhook_response.json()["processed"] is True

    paid_order = client.get(f"/api/v1/orders/{order_id}")
    assert paid_order.json()["status"] == "paid"


def test_cart_rejects_insufficient_stock(client: TestClient) -> None:
    product_response = client.post(
        "/api/v1/products",
        json={
            "sku": "SKU-LOW",
            "name": "Limited Item",
            "description": "",
            "category": "limited",
            "price": "19.00",
            "stock_on_hand": 1,
            "status": "active",
        },
    )
    assert product_response.status_code == 201

    cart_response = client.post(
        "/api/v1/cart/11111111-1111-1111-1111-111111111111/items",
        json={"sku": "SKU-LOW", "quantity": 2},
    )
    assert cart_response.status_code == 409


def _extract_input_value_after(html: str, label: str) -> str:
    start = html.index(label)
    marker = 'value="'
    value_start = html.index(marker, start) + len(marker)
    value_end = html.index('"', value_start)
    return html[value_start:value_end]


def _extract_hidden_value(html: str, name: str) -> str:
    marker = f'name="{name}" value="'
    start = html.index(marker) + len(marker)
    end = html.index('"', start)
    return html[start:end]


def _extract_api_key_id_for_name(html: str, name: str) -> str:
    row_start = html.rfind("<tr>", 0, html.index(name))
    marker = "/admin/api-keys/"
    start = html.index(marker, row_start) + len(marker)
    end = html.index("/", start)
    return html[start:end]
