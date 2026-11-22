"""Middlewares: request-id, autenticación por API key, rate limit y métricas."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections import defaultdict, deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from .config import Settings
from .services.monitoring import Monitoring
from .services.store import Store

logger = logging.getLogger(__name__)

# /metrics se deja sin API key para que Prometheus pueda hacer scraping; solo
# expone contadores y gauges agregados, no datos de negocio.
_EXEMPT_AUTH = {
    "/",
    "/v1/health",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
}
_SKIP_EVENTS = {"/metrics", "/v1/health", "/docs", "/redoc", "/openapi.json", "/"}

_ID_PATTERNS = (
    re.compile(r"^(/v1/analyses/)[^/]+$"),
    re.compile(r"^(/v1/sources/jobs/)[^/]+$"),
)


def metric_path(path: str) -> str:
    for pattern in _ID_PATTERNS:
        match = pattern.match(path)
        if match:
            return f"{match.group(1)}{{id}}"
    return path


class AccessMiddleware(BaseHTTPMiddleware):
    """Middleware único para no depender del orden de ``add_middleware``."""

    def __init__(
        self,
        app,  # type: ignore[no-untyped-def]
        *,
        settings: Settings,
        monitoring: Monitoring,
        store: Store,
        engine_name: str,
    ) -> None:
        super().__init__(app)
        self.settings = settings
        self.monitoring = monitoring
        self.store = store
        self.engine_name = engine_name
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    # ------------------------------------------------------------------
    def _client_id(self, request: Request) -> str:
        api_key = self._api_key(request)
        if api_key:
            return f"key:{api_key[:12]}"
        return f"ip:{request.client.host if request.client else 'unknown'}"

    @staticmethod
    def _api_key(request: Request) -> str | None:
        header = request.headers.get("x-api-key")
        if header:
            return header.strip()
        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            return authorization[7:].strip()
        return None

    def _rate_limited(self, client_id: str) -> bool:
        limit = self.settings.rate_limit_requests
        window = self.settings.rate_limit_window_seconds
        if limit <= 0 or window <= 0:
            return False
        now = time.monotonic()
        bucket = self._hits[client_id]
        while bucket and now - bucket[0] > window:
            bucket.popleft()
        if len(bucket) >= limit:
            return True
        bucket.append(now)
        return False

    # ------------------------------------------------------------------
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        started = time.perf_counter()
        path = request.url.path

        if request.method != "OPTIONS" and path not in _EXEMPT_AUTH:
            if self.settings.auth_enabled:
                provided = self._api_key(request)
                if not provided or provided != self.settings.api_key:
                    return self._json_error(
                        request,
                        request_id,
                        401,
                        "unauthorized",
                        "API key inválida o ausente. Usa el header X-API-Key.",
                        started,
                    )
            if self._rate_limited(self._client_id(request)):
                return self._json_error(
                    request,
                    request_id,
                    429,
                    "rate_limited",
                    "Demasiadas peticiones. Intenta de nuevo en unos segundos.",
                    started,
                    extra_headers={
                        "Retry-After": str(self.settings.rate_limit_window_seconds)
                    },
                )

        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            latency = time.perf_counter() - started
            self._observe(request, status_code, latency, request_id)
            raise
        latency = time.perf_counter() - started
        self._observe(request, status_code, latency, request_id)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = f"{latency * 1000:.2f}"
        return response

    # ------------------------------------------------------------------
    def _observe(
        self, request: Request, status_code: int, latency: float, request_id: str
    ) -> None:
        path = metric_path(request.url.path)
        self.monitoring.observe_request(
            request.method, path, status_code, latency
        )
        if self.settings.store_events and request.url.path not in _SKIP_EVENTS:
            self.store.record_event(
                request_id=request_id,
                method=request.method,
                path=path,
                status_code=status_code,
                latency_ms=round(latency * 1000, 2),
                client=request.client.host if request.client else "",
                engine=self.engine_name,
            )

    def _json_error(
        self,
        request: Request,
        request_id: str,
        status_code: int,
        code: str,
        message: str,
        started: float,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> JSONResponse:
        latency = time.perf_counter() - started
        self._observe(request, status_code, latency, request_id)
        headers = {"X-Request-ID": request_id, "X-Process-Time-Ms": f"{latency * 1000:.2f}"}
        if extra_headers:
            headers.update(extra_headers)
        return JSONResponse(
            status_code=status_code,
            content={"error": {"code": code, "message": message, "detail": None}},
            headers=headers,
        )
