"""Request dependencies: the authenticated user and client details.

``CurrentAuth`` is the only way route handlers obtain the user. It shares the
request's single database transaction (``DbSession``), in which it has set
``app.user_id`` for RLS.
"""

from typing import Annotated

from fastapi import Depends, Request

from app.core.client_ip import client_ip
from app.core.config import Settings
from app.core.errors import AuthenticationError
from app.db.session import DbSession
from app.modules.identity.cookies import read_session_cookie
from app.modules.identity.service import AuthenticatedUser, ClientInfo, authenticate


def get_settings_from_app(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


AppSettings = Annotated[Settings, Depends(get_settings_from_app)]


def get_client_info(request: Request, settings: AppSettings) -> ClientInfo:
    return ClientInfo(ip=client_ip(request, settings), user_agent=request.headers.get("user-agent"))


Client = Annotated[ClientInfo, Depends(get_client_info)]


async def get_optional_auth(
    request: Request, db: DbSession, settings: AppSettings
) -> AuthenticatedUser | None:
    token = read_session_cookie(request, settings)
    if token is None:
        return None
    return await authenticate(db, settings, token)


OptionalAuth = Annotated[AuthenticatedUser | None, Depends(get_optional_auth)]


async def require_auth(auth: OptionalAuth) -> AuthenticatedUser:
    if auth is None:
        raise AuthenticationError()
    return auth


CurrentAuth = Annotated[AuthenticatedUser, Depends(require_auth)]
