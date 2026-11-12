"""Error types and the standard error envelope.

Every error response has the same shape (see docs/API_CONTRACTS.md):

    {"error": {"code": "...", "message": "...", "details": [...]},
     "meta": {"request_id": "..."}}

Services raise ``AppError`` subclasses; route handlers never build error
responses by hand. Unexpected exceptions are logged with a traceback and
returned as a generic 500 without internal detail.
"""

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger
from app.core.request_context import REQUEST_ID_HEADER

logger = get_logger("app.errors")


class AppError(Exception):
    """Base class for expected, client-facing errors."""

    status_code: int = HTTPStatus.BAD_REQUEST
    code: str = "BAD_REQUEST"
    message: str = "The request could not be processed."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details or []
        self.headers = headers or {}
        super().__init__(self.message)


class NotFoundError(AppError):
    # Also used for cross-tenant access, so existence is never revealed.
    status_code = HTTPStatus.NOT_FOUND
    code = "NOT_FOUND"
    message = "Resource not found."


class ConflictError(AppError):
    status_code = HTTPStatus.CONFLICT
    code = "CONFLICT"
    message = "The request conflicts with the current state."


class PermissionDeniedError(AppError):
    status_code = HTTPStatus.FORBIDDEN
    code = "PERMISSION_DENIED"
    message = "You do not have permission to perform this action."


class AuthenticationError(AppError):
    status_code = HTTPStatus.UNAUTHORIZED
    code = "UNAUTHENTICATED"
    message = "Authentication required."


class RateLimitedError(AppError):
    status_code = HTTPStatus.TOO_MANY_REQUESTS
    code = "RATE_LIMITED"
    message = "Too many attempts. Please wait and try again."

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(headers={"Retry-After": str(max(1, retry_after_seconds))})


_HTTP_STATUS_CODES: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHENTICATED",
    403: "PERMISSION_DENIED",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    429: "RATE_LIMITED",
}


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def envelope_response(
    *,
    status_code: int,
    code: str,
    message: str,
    request_id: str | None,
    details: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """The standard error envelope; also usable directly as an ASGI app in middleware."""
    response_headers = dict(headers or {})
    if request_id:
        response_headers[REQUEST_ID_HEADER] = request_id
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {"code": code, "message": message, "details": details or []},
            "meta": {"request_id": request_id},
        },
        headers=response_headers,
    )


def error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return envelope_response(
        status_code=status_code,
        code=code,
        message=message,
        request_id=_request_id(request),
        details=details,
        headers=headers,
    )


async def _app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppError):  # pragma: no cover - registration guarantees type
        raise exc
    return error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
        headers=exc.headers,
    )


async def _validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(
        exc, RequestValidationError
    ):  # pragma: no cover - registration guarantees type
        raise exc
    # Only location, message and type: never echo the submitted value back,
    # it may be a password or personal data.
    details = [
        {
            "field": ".".join(str(part) for part in err.get("loc", ())),
            "message": err.get("msg", "Invalid value."),
            "type": err.get("type", "value_error"),
        }
        for err in exc.errors()
    ]
    return error_response(
        request,
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        code="VALIDATION_ERROR",
        message="The request contains invalid fields.",
        details=details,
    )


async def _http_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(
        exc, StarletteHTTPException
    ):  # pragma: no cover - registration guarantees type
        raise exc
    code = _HTTP_STATUS_CODES.get(exc.status_code, "HTTP_ERROR")
    try:
        message = HTTPStatus(exc.status_code).phrase + "."
    except ValueError:
        message = "Request failed."
    return error_response(
        request,
        status_code=exc.status_code,
        code=code,
        message=message,
        headers=dict(exc.headers) if exc.headers else None,
    )


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Fallback only: CatchAllErrorsMiddleware normally handles these first, inside
    # CORS. This runs if an exception escapes the outermost middleware.
    logger.error(
        "unhandled_exception",
        exc_info=exc,
        method=request.method,
        path=request.url.path,
        request_id=_request_id(request),
    )
    return error_response(
        request,
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        code="INTERNAL_ERROR",
        message="An unexpected error occurred.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)
