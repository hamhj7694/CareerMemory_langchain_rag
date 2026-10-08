"""민감 원문을 기록하지 않는 요청 지연·오류율 관측 도구."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import logging
from math import ceil
from threading import Lock
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request


logger = logging.getLogger("career_memory.http")


@dataclass(frozen=True)
class RouteMetrics:
    method: str
    route: str
    count: int
    error_count: int
    error_rate: float
    p50_ms: float
    p95_ms: float


class RequestMetricsRegistry:
    def __init__(self, max_samples_per_route: int = 2_000) -> None:
        self._durations: dict[tuple[str, str], deque[float]] = defaultdict(
            lambda: deque(maxlen=max_samples_per_route)
        )
        self._counts: dict[tuple[str, str], int] = defaultdict(int)
        self._errors: dict[tuple[str, str], int] = defaultdict(int)
        self._lock = Lock()

    def record(self, method: str, route: str, status_code: int, duration_ms: float) -> None:
        key = (method.upper(), route)
        with self._lock:
            self._counts[key] += 1
            if status_code >= 400:
                self._errors[key] += 1
            self._durations[key].append(max(0.0, duration_ms))

    def snapshot(self) -> list[RouteMetrics]:
        with self._lock:
            keys = sorted(self._counts)
            values = []
            for method, route in keys:
                samples = sorted(self._durations[(method, route)])
                count = self._counts[(method, route)]
                errors = self._errors[(method, route)]
                values.append(RouteMetrics(
                    method=method,
                    route=route,
                    count=count,
                    error_count=errors,
                    error_rate=round(errors / max(1, count), 6),
                    p50_ms=round(_percentile(samples, 0.50), 3),
                    p95_ms=round(_percentile(samples, 0.95), 3),
                ))
            return values

    def clear(self) -> None:
        with self._lock:
            self._durations.clear()
            self._counts.clear()
            self._errors.clear()


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    index = max(0, min(len(values) - 1, ceil(len(values) * percentile) - 1))
    return values[index]


request_metrics = RequestMetricsRegistry()


def register_operational_metrics(app: FastAPI) -> None:
    @app.middleware("http")
    async def observe_request(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", "").strip() or str(uuid4())
        request.state.request_id = request_id
        started = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            duration_ms = (perf_counter() - started) * 1_000
            route_object = request.scope.get("route")
            # 매칭되지 않은 raw URL에는 사용자 입력이나 opaque ID가 포함될 수 있으므로
            # route template을 찾지 못했을 때 실제 path를 로그·metric label로 쓰지 않는다.
            route_template = getattr(route_object, "path", None)
            route = str(route_template or "<unmatched>")
            request_metrics.record(
                request.method,
                route,
                status_code,
                duration_ms,
            )
            # URL query/body/사용자 원문은 의도적으로 기록하지 않는다.
            logger.info(
                "request_completed request_id=%s method=%s route=%s status=%s duration_ms=%.3f",
                request_id,
                request.method,
                route,
                status_code,
                duration_ms,
            )


__all__ = [
    "RequestMetricsRegistry",
    "RouteMetrics",
    "register_operational_metrics",
    "request_metrics",
]
