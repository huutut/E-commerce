from collections.abc import Awaitable, Callable
from inspect import isgenerator
from typing import cast

from fastapi import Request
from fastapi.responses import RedirectResponse, Response
from sqlmodel import Session

from commerce.api.deps import session_dep
from commerce.core.database import get_engine
from commerce.services.security import SESSION_COOKIE_NAME, get_admin_from_cookie

PUBLIC_ADMIN_PATHS = {"/admin/login"}


async def admin_auth_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    if not request.url.path.startswith("/admin") or request.url.path in PUBLIC_ADMIN_PATHS:
        return await call_next(request)

    admin = _get_admin_for_request(request)

    if admin is None:
        if request.url.path == "/admin/logout":
            return RedirectResponse("/admin/login", status_code=303)
        return RedirectResponse(f"/admin/login?next={request.url.path}", status_code=303)

    request.state.admin = admin
    return await call_next(request)


def _get_admin_for_request(request: Request) -> object | None:
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    override = request.app.dependency_overrides.get(session_dep)
    if override is None:
        with Session(get_engine()) as session:
            return get_admin_from_cookie(session, cookie)

    resource = override()
    if isgenerator(resource):
        try:
            session = cast(Session, next(resource))
            return get_admin_from_cookie(session, cookie)
        finally:
            resource.close()

    if isinstance(resource, Session):
        return get_admin_from_cookie(resource, cookie)
    return None
