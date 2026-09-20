from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from redis import Redis
from sqlmodel import Session

from commerce.core.cache import get_redis_client
from commerce.core.config import get_settings
from commerce.core.database import get_session
from commerce.domain.models import ApiKey
from commerce.repositories.api_access_logs import record_api_access
from commerce.repositories.api_keys import authenticate_api_key
from commerce.services.security import extract_api_key_prefix


def session_dep() -> Generator[Session, None, None]:
    yield from get_session()


def redis_dep() -> Redis:
    return get_redis_client()


def api_key_dep(
    request: Request,
    session: Annotated[Session, Depends(session_dep)],
    redis: Annotated[Redis, Depends(redis_dep)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> ApiKey:
    key_prefix = extract_api_key_prefix(x_api_key or "") or ""
    api_key = authenticate_api_key(session, x_api_key)
    if api_key is None:
        record_api_access(
            session,
            api_key=None,
            key_prefix=key_prefix,
            method=request.method,
            path=request.url.path,
            status="unauthorized",
            status_code=401,
        )
        session.commit()
        raise HTTPException(status_code=401, detail="Valid X-API-Key header is required.")
    if _rate_limited(redis, api_key):
        record_api_access(
            session,
            api_key=api_key,
            key_prefix=api_key.key_prefix,
            method=request.method,
            path=request.url.path,
            status="rate_limited",
            status_code=429,
        )
        session.commit()
        raise HTTPException(status_code=429, detail="API rate limit exceeded.")
    record_api_access(
        session,
        api_key=api_key,
        key_prefix=api_key.key_prefix,
        method=request.method,
        path=request.url.path,
        status="accepted",
        status_code=200,
    )
    session.commit()
    return api_key


SessionDep = Annotated[Session, Depends(session_dep)]
RedisDep = Annotated[Redis, Depends(redis_dep)]
ApiKeyDep = Annotated[ApiKey, Depends(api_key_dep)]


def _rate_limited(redis: Redis, api_key: ApiKey) -> bool:
    settings = get_settings()
    key = f"rate-limit:api-key:{api_key.key_prefix}"
    try:
        current = redis.incr(key)
        if int(current) == 1:
            redis.expire(key, settings.api_rate_limit_window_seconds)
        return int(current) > settings.api_rate_limit_requests
    except Exception:
        return False
