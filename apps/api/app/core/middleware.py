"""Request-scoped middleware: request id + structured access logging."""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger

log = get_logger("http")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request id, bind it to the log context, and log each request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["x-request-id"] = request_id
        # Skip noise from health probes.
        if not request.url.path.startswith(("/healthz", "/readyz")):
            log.info(
                "request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=elapsed_ms,
                request_id=request_id,
            )
        return response
