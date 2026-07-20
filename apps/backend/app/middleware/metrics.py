"""
Exposes a /metrics endpoint in Prometheus's text exposition format. Scraped by the
prometheus service defined in infra/docker/docker-compose.monitoring.yml.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

REQUEST_COUNT = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "path", "status_code"]
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds", "HTTP request latency", ["method", "path"]
)
ORDERS_PLACED = Counter("orders_placed_total", "Orders placed", ["status", "broker_type"])
BROKER_ERRORS = Counter("broker_errors_total", "Broker adapter errors", ["broker_type", "error_type"])


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        # Use the route template (e.g. "/api/accounts/{account_id}/positions"), not
        # the raw path, so per-resource-id cardinality doesn't blow up Prometheus's
        # label space.
        path = request.scope.get("route").path if request.scope.get("route") else request.url.path

        REQUEST_COUNT.labels(request.method, path, response.status_code).inc()
        REQUEST_LATENCY.labels(request.method, path).observe(duration)
        return response


router = APIRouter()


@router.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
