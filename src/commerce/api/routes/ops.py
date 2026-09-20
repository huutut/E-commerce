from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import PlainTextResponse

from commerce.api.deps import RedisDep, SessionDep
from commerce.core.config import get_settings
from commerce.core.metrics import registry

router = APIRouter(prefix="/ops", tags=["ops"])


@router.get("/metrics", response_class=PlainTextResponse)
def metrics(x_ops_token: str | None = Header(default=None, alias="X-Ops-Token")) -> str:
    settings = get_settings()
    if settings.ops_metrics_token and x_ops_token != settings.ops_metrics_token:
        raise HTTPException(status_code=401, detail="Valid X-Ops-Token header is required.")
    return registry.render_prometheus()


@router.get("/status")
def ops_status(session: SessionDep, redis: RedisDep) -> dict[str, object]:
    database_ok = True
    redis_ok = True
    try:
        session.connection()
    except Exception:
        database_ok = False
    try:
        redis.ping()
    except Exception:
        redis_ok = False
    return {
        "status": "ok" if database_ok and redis_ok else "degraded",
        "database": database_ok,
        "redis": redis_ok,
    }
