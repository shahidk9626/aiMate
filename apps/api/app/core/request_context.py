"""Request id middleware and access logging.

Implemented as pure ASGI middleware (not ``BaseHTTPMiddleware``) so it adds no
overhead and works with streaming responses such as the SSE endpoints planned
for the inbox and widget.
"""

import re
import time
import uuid

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import get_logger

REQUEST_ID_HEADER = "X-Request-ID"
# Accept a caller-supplied id only if it is short and harmless to log/echo.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

logger = get_logger("app.access")


def _incoming_request_id(scope: Scope) -> str | None:
    wanted = REQUEST_ID_HEADER.lower().encode("latin-1")
    for key, value in scope.get("headers", []):
        if key == wanted:
            candidate = value.decode("latin-1")
            return candidate if _SAFE_REQUEST_ID.fullmatch(candidate) else None
    return None


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope) or uuid.uuid4().hex
        # Shared with Request.state so exception handlers can read it.
        scope.setdefault("state", {})["request_id"] = request_id

        status_code = 500
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        with structlog.contextvars.bound_contextvars(request_id=request_id):
            try:
                await self.app(scope, receive, send_wrapper)
            finally:
                logger.info(
                    "request",
                    method=scope["method"],
                    # Path only: query strings can carry personal data.
                    path=scope["path"],
                    status=status_code,
                    duration_ms=round((time.perf_counter() - started) * 1000, 2),
                )
