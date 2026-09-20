from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from commerce.api.admin_auth import admin_auth_middleware
from commerce.api.errors import http_exception_handler, unhandled_exception_handler
from commerce.api.routes import (
    admin,
    cart,
    customers,
    health,
    ops,
    orders,
    payments,
    products,
    store,
)
from commerce.core.config import get_settings
from commerce.core.metrics import metrics_middleware


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, debug=settings.app_debug)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(admin_auth_middleware)
    app.middleware("http")(metrics_middleware)
    app.exception_handler(StarletteHTTPException)(http_exception_handler)
    app.exception_handler(Exception)(unhandled_exception_handler)
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=settings.upload_dir), name="media")

    app.include_router(health.router)
    app.include_router(ops.router)
    app.include_router(store.router)
    app.include_router(customers.router, prefix=settings.api_v1_prefix)
    app.include_router(products.router, prefix=settings.api_v1_prefix)
    app.include_router(cart.router, prefix=settings.api_v1_prefix)
    app.include_router(orders.router, prefix=settings.api_v1_prefix)
    app.include_router(payments.router, prefix=settings.api_v1_prefix)
    app.include_router(admin.router)
    return app


app = create_app()
