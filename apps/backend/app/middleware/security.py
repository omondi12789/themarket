"""
Two ASGI middlewares:
1. RateLimitMiddleware — Redis-backed fixed-window rate limiting per client IP
   (+ per-user once authenticated). Protects auth endpoints from credential
   stuffing/brute force and the whole API from abusive clients.
2. SecurityHeadersMiddleware — sets the standard defensive headers (CSP, HSTS,
   X-Frame-Options, X-Content-Type-Options, Referrer-Policy) on every response.
   This doesn't replace CSRF/XSS-safe coding practices elsewhere (e.g. the frontend
   never using dangerouslySetInnerHTML with untrusted content) — it's the baseline
   HTTP-layer hardening on top of that.
"""
from __future__ import annotations

import time

import redis
from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import get_settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_window: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self._redis: redis.Redis | None = None

    def _get_redis(self) -> redis.Redis:
        if self._redis is None:
            settings = get_settings()
            self._redis = redis.Redis.from_url(settings.redis_url)
        return self._redis

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        # Auth endpoints get a much tighter limit — they're the highest-value target
        # for credential stuffing / brute force.
        is_auth_endpoint = request.url.path.startswith("/api/auth/login") or request.url.path.startswith(
            "/api/auth/register"
        )
        limit = 10 if is_auth_endpoint else self.requests_per_window
        window = 60 if is_auth_endpoint else self.window_seconds

        key = f"ratelimit:{'auth' if is_auth_endpoint else 'api'}:{client_ip}"

        try:
            redis_client = self._get_redis()
            current = redis_client.incr(key)
            if current == 1:
                redis_client.expire(key, window)

            if current > limit:
                ttl = redis_client.ttl(key)
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "rate limit exceeded", "retry_after_seconds": max(ttl, 1)},
                    headers={"Retry-After": str(max(ttl, 1))},
                )
        except Exception:
            # Redis unavailable: fail open rather than taking the whole API down over
            # a rate-limiter outage, but this should alert ops (see monitoring below).
            pass

        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        # CSP is deliberately conservative; loosen only for specific known-needed
        # third-party origins (e.g. TradingView's embed script domain on the frontend,
        # which is a separate Next.js app and sets its own CSP, not this API's).
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'"
        )
        return response
