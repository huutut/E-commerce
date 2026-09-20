from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from time import perf_counter

from fastapi import Request
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response


@dataclass
class MetricsRegistry:
    total_requests: int = 0
    total_errors: int = 0
    total_duration_seconds: float = 0.0
    by_route: dict[tuple[str, str, int], int] = field(default_factory=dict)
    lock: Lock = field(default_factory=Lock)

    def record(self, method: str, path: str, status_code: int, duration_seconds: float) -> None:
        normalized_path = _normalize_path(path)
        with self.lock:
            self.total_requests += 1
            self.total_duration_seconds += duration_seconds
            if status_code >= 500:
                self.total_errors += 1
            key = (method, normalized_path, status_code)
            self.by_route[key] = self.by_route.get(key, 0) + 1

    def render_prometheus(self) -> str:
        with self.lock:
            lines = [
                "# HELP commerce_requests_total Total HTTP requests.",
                "# TYPE commerce_requests_total counter",
                f"commerce_requests_total {self.total_requests}",
                "# HELP commerce_errors_total Total HTTP 5xx responses.",
                "# TYPE commerce_errors_total counter",
                f"commerce_errors_total {self.total_errors}",
                "# HELP commerce_request_duration_seconds_sum Total request duration seconds.",
                "# TYPE commerce_request_duration_seconds_sum counter",
                f"commerce_request_duration_seconds_sum {self.total_duration_seconds:.6f}",
                "# HELP commerce_route_requests_total Total HTTP requests by route.",
                "# TYPE commerce_route_requests_total counter",
            ]
            for (method, path, status_code), count in sorted(self.by_route.items()):
                lines.append(
                    'commerce_route_requests_total{'
                    f'method="{method}",path="{path}",status_code="{status_code}"'
                    f"}} {count}"
                )
            return "\n".join(lines) + "\n"


registry = MetricsRegistry()


async def metrics_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
    start = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        registry.record(request.method, request.url.path, 500, perf_counter() - start)
        raise
    registry.record(request.method, request.url.path, response.status_code, perf_counter() - start)
    return response


def _normalize_path(path: str) -> str:
    if path.startswith("/media/"):
        return "/media/*"
    return path
