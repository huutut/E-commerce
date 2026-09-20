from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.exceptions import HTTPException as StarletteHTTPException

_TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"
_templates = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)

_ERROR_TITLES = {
    400: "请求有误",
    401: "请先登录",
    403: "权限不足",
    404: "页面未找到",
    409: "操作冲突",
    429: "请求过于频繁",
    500: "系统异常",
    503: "服务暂不可用",
}


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> Response:
    if _is_admin_page(request):
        return _render_admin_error(request, exc.status_code, str(exc.detail))
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)


async def unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    if _is_admin_page(request):
        return _render_admin_error(request, 500, "系统处理请求时出现异常，请稍后重试。")
    return JSONResponse({"detail": "Internal Server Error"}, status_code=500)


def _is_admin_page(request: Request) -> bool:
    return request.url.path.startswith("/admin")


def _render_admin_error(request: Request, status_code: int, detail: str) -> HTMLResponse:
    title = _ERROR_TITLES.get(status_code, "请求失败")
    template = _templates.get_template("admin/error.html")
    html = template.render(
        request=request,
        title=title,
        status_code=status_code,
        detail=detail,
        back_url=_back_url(request),
        current_admin=getattr(request.state, "admin", None),
    )
    return HTMLResponse(html, status_code=status_code)


def _back_url(request: Request) -> str:
    admin = getattr(request.state, "admin", None)
    return "/admin" if admin else "/admin/login"
