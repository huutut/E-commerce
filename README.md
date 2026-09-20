# Commerce Platform

Python FastAPI + PostgreSQL SQLModel + Redis + Playwright e-commerce foundation.

## Why this layout

- `FastAPI` exposes versioned HTTP APIs.
- `SQLModel` owns typed PostgreSQL persistence.
- `Redis` stores hot cart state and is ready for caching, rate limits, and jobs.
- `Playwright` is included for browser-level regression tests.
- Docker is not required. This works with native Windows services or managed cloud services.

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
copy .env.example .env
```

Install services without Docker:

- PostgreSQL: install from EnterpriseDB or use a managed PostgreSQL instance.
- Redis: install Memurai Developer, Redis for Windows alternatives, or use a managed Redis instance.

Then update `.env` and initialize tables:

```powershell
alembic upgrade head
python scripts/seed.py
uvicorn commerce.main:app --reload
```

Or use the Windows helper:

```powershell
.\scripts\start_dev.ps1
```

For quick local experiments only, `python scripts/init_db.py` can create tables directly.

For a native Windows production-style run without Docker:

```powershell
copy .env.production.example .env
# Fill database, Redis, session, payment, shipping, and metrics secrets.
.\scripts\start_prod.ps1
.\scripts\check_prod.ps1
```

## API surface

- `GET /admin/login` Chinese admin login page
- `GET /admin` Chinese operations dashboard
- `GET /admin/products` product management page
- `GET /admin/orders` order management page
- `GET /admin/orders/export` filtered order CSV export
- `GET /admin/customers` customer management page
- `GET /admin/sandbox` customer, cart, and checkout test page
- `GET /admin/audit` admin audit log page
- `GET /admin/api-keys` API Key management page
- `GET /admin/reports` report center
- `/admin/*` Chinese HTML error pages for common 400/403/404/409/429/500 failures
- `GET /store` Chinese storefront with customer, cart, checkout, and order confirmation flows
- `POST /api/v1/payments/orders/{order_id}/checkout` payment checkout session creation
- `POST /api/v1/payments/webhooks/{provider}` signed payment webhook receiver
- `GET /ops/metrics` Prometheus-style runtime metrics
- `GET /ops/status` operations health summary
- `GET /health/live`
- `GET /health/ready`
- `POST /api/v1/customers`
- `POST /api/v1/products`
- `GET /api/v1/products`
- `GET /api/v1/products/{sku}`
- `POST /api/v1/cart/{customer_id}/items`
- `GET /api/v1/cart/{customer_id}`
- `DELETE /api/v1/cart/{customer_id}`
- `POST /api/v1/orders/checkout`
- `GET /api/v1/orders/{order_id}`

## Tests

```powershell
pytest
ruff check .
mypy src tests
```

Browser tests are prepared under `e2e/`. After installing Playwright browsers:

```powershell
playwright install chromium
RUN_E2E=1 pytest e2e
```

## Production readiness

- Chinese storefront pages backed by the same catalog, Redis cart, and SQLModel order flow.
- Local product image upload mounted under `/media`.
- Configurable payment checkout sessions plus signed webhook ingestion for provider integration.
- Shipment records and tracking URLs generated from fulfillment updates.
- Explicit admin permission matrix for owner/operator capabilities.
- Prometheus-style `/ops/metrics` and `/ops/status` endpoints for monitoring.
- Windows-native start/check scripts for environments where Docker is unavailable.

## Manual web test

Open the Chinese admin dashboard:

```text
http://127.0.0.1:8000/admin
```

Development admin account created by `python scripts/seed.py`:

```text
邮箱：admin@example.com
密码：Admin@123456
```

Development API key created by `python scripts/seed.py`:

```text
X-API-Key: ck_live_dev.local-development-api-key
```

For non-local environments, set a strong `ADMIN_SESSION_SECRET` with at least 32 characters.
Use `ADMIN_COOKIE_SECURE=true` behind HTTPS.

Recommended flow:

1. Log in from `后台登录`.
2. Open `商品管理` and create a product with a low-stock threshold.
3. Edit the product price, stock, low-stock threshold, or listing status.
4. Use product filters for keyword, category, status, and low stock.
5. Open the product edit page and submit an inventory adjustment.
6. Review the inventory adjustment history on the product edit page.
7. Open `流程测试` and create or load a test customer.
8. Add a product to the cart.
9. Submit checkout.
10. Confirm the generated order in `订单管理`.
11. Review dashboard sales amount, order status distribution, and low-stock products.
12. Filter orders by order ID, customer name/email, status, and date range.
13. Export the current order filter as CSV.
14. Open order detail and use `模拟支付成功`.
15. Save order note, carrier, and tracking number.
16. Move the order through `已履约`.
17. Create a return request and complete it to mark payment as refunded.
18. Open `客户管理` and search by customer name or email.
19. Review the customer's history and total spend.
20. Open `报表中心` and export report CSV.
21. Open `管理员`, create an operator account, update a role, and test enable/disable.
22. Open `API Key`, create a key, call `/api/v1/products` with `X-API-Key`, then disable the key.
23. Open `账号安全`, verify password validation, and update the current password.
24. Open `审计日志` and confirm failed login, password, API Key, product, inventory, admin, customer, cart, checkout, payment, return, and order status actions were recorded.
