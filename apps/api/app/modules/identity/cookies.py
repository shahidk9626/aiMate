"""Session cookie attributes (ADR-023 decision A).

HttpOnly (JavaScript cannot read it), SameSite=Lax (not sent on cross-site
POSTs), Path=/, no Domain (host-only on the API domain). Secure and the
__Host- prefix everywhere except local development and tests.
"""

from fastapi import Request, Response

from app.core.config import Settings


def set_session_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_absolute_days * 24 * 3600,
        path="/",
        secure=settings.cookies_secure,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        secure=settings.cookies_secure,
        httponly=True,
        samesite="lax",
    )


def read_session_cookie(request: Request, settings: Settings) -> str | None:
    value = request.cookies.get(settings.session_cookie_name)
    # Reject obviously malformed values before any database lookup.
    if not value or len(value) > 256:
        return None
    return value
