from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError

from fastapi import APIRouter

from commerce.core.cache import check_redis
from commerce.core.database import check_database

router = APIRouter(prefix="/health", tags=["health"])
_probe_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="health-probe")
_PROBE_TIMEOUT_SECONDS = 2.5


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready() -> dict[str, bool | str]:
    database_ok, database_error = _run_probe(check_database)
    redis_ok, redis_error = _run_probe(check_redis)

    return {
        "status": "ok" if database_ok and redis_ok else "degraded",
        "database": database_ok,
        "redis": redis_ok,
        "database_error": database_error,
        "redis_error": redis_error,
    }


def _run_probe(probe: Callable[[], bool]) -> tuple[bool, str]:
    future = _probe_executor.submit(probe)
    try:
        return future.result(timeout=_PROBE_TIMEOUT_SECONDS), ""
    except TimeoutError:
        return False, "probe timed out"
    except Exception as exc:
        return False, str(exc)
