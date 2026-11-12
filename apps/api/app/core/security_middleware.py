"""Request-level security middleware (Stage 2, ADR-023). All pure ASGI.

Order, outermost first (see ``create_app``):
  CORS → request id → security headers → catch-all errors → body limit → CSRF → app

so every response, including rejections and crashes, carries CORS headers,
an X-Request-ID and the security headers.
"""

from http import HTTPStatus

from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import envelope_response
from app.core.logging import get_logger

logger = get_logger("app.errors")

API_PREFIX = "/api/v1/"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# Authenticated by other means (provider signatures, widget tokens), called
# by servers or third-party sites: no CSRF header/Origin requirement.
CSRF_EXEMPT_PREFIXES = ("/api/v1/webhooks/", "/api/v1/widget/")
CSRF_HEADER = "x-requested-with"
CSRF_HEADER_VALUE = "leadflow"

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


def _request_id(scope: Scope) -> str | None:
    state = scope.get("state") or {}
    value = state.get("request_id")
    return value if isinstance(value, str) else None


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_api = scope["path"].startswith(API_PREFIX)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in _SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
                if is_api:
                    # API responses can contain personal data: never cache them.
                    headers.setdefault("Cache-Control", "no-store")
            await send(message)

        await self.app(scope, receive, send_wrapper)


class CatchAllErrorsMiddleware:
    """Turns unexpected exceptions into the 500 envelope *inside* CORS.

    Starlette's own error middleware sits outside all user middleware, so its
    500 responses lacked CORS headers and browsers reported a network error.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            if started:  # too late to send a clean error response
                raise
            request_id = _request_id(scope)
            logger.error(
                "unhandled_exception",
                exc_info=exc,
                method=scope["method"],
                path=scope["path"],
                request_id=request_id,
            )
            response = envelope_response(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                code="INTERNAL_ERROR",
                message="An unexpected error occurred.",
                request_id=request_id,
            )
            await response(scope, receive, send)


class _BodyTooLargeError(HTTPException):
    # An HTTPException on purpose: FastAPI turns other exceptions raised while
    # reading the body into a generic 400, but re-raises HTTPExceptions, which
    # the app's handler renders as the PAYLOAD_TOO_LARGE envelope.
    def __init__(self) -> None:
        super().__init__(status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)


class BodySizeLimitMiddleware:
    """Rejects request bodies over ``max_bytes`` (declared or actually sent)."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    def _reject(self, scope: Scope) -> ASGIApp:
        return envelope_response(
            status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            code="PAYLOAD_TOO_LARGE",
            message=f"Request body exceeds {self.max_bytes} bytes.",
            request_id=_request_id(scope),
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = Headers(scope=scope).get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            await self._reject(scope)(scope, receive, send)
            return

        received = 0
        started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLargeError()
            return message

        async def send_wrapper(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, send_wrapper)
        except _BodyTooLargeError:
            if started:
                raise
            await self._reject(scope)(scope, receive, send)


class CSRFMiddleware:
    """Blocks cross-site state changes on cookie-authenticated API routes.

    Unsafe methods under /api/v1 must send ``X-Requested-With: leadflow``. A
    custom header cannot be sent cross-site without a CORS preflight, which
    only WEB_ORIGIN passes. If the browser sends an Origin, it must equal
    WEB_ORIGIN. Non-browser clients (no Origin) need only the header.
    Defence in depth on top of SameSite=Lax cookies.
    """

    def __init__(self, app: ASGIApp, trusted_origin: str) -> None:
        self.app = app
        self.trusted_origin = trusted_origin

    def _allowed(self, scope: Scope) -> bool:
        headers = Headers(scope=scope)
        if headers.get(CSRF_HEADER, "").lower() != CSRF_HEADER_VALUE:
            return False
        origin = headers.get("origin")
        return origin is None or origin == self.trusted_origin

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path: str = scope.get("path", "")
        if (
            scope["type"] == "http"
            and scope["method"] in UNSAFE_METHODS
            and path.startswith(API_PREFIX)
            and not path.startswith(CSRF_EXEMPT_PREFIXES)
            and not self._allowed(scope)
        ):
            logger.warning("csrf_rejected", method=scope["method"], path=path)
            response = envelope_response(
                status_code=HTTPStatus.FORBIDDEN,
                code="CSRF_REJECTED",
                message="Request rejected: missing or untrusted request origin.",
                request_id=_request_id(scope),
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
