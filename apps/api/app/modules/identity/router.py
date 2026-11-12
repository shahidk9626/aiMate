"""HTTP routes for authentication and the current user (docs/API_CONTRACTS.md, Stage 2).

Thin by design: parse input, call the service, set/clear the session cookie.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rate_limit import RateLimiter, get_rate_limiter
from app.core.responses import Envelope, envelope
from app.db.session import DbSession
from app.modules.identity import service
from app.modules.identity.cookies import clear_session_cookie, set_session_cookie
from app.modules.identity.dependencies import AppSettings, Client, CurrentAuth, OptionalAuth
from app.modules.identity.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    MeOut,
    SignupRequest,
    UpdateProfileRequest,
)

router = APIRouter(tags=["auth"])

Limiter = Annotated[RateLimiter, Depends(get_rate_limiter)]


def _session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.db_session_factory
    return factory


SessionFactory = Annotated[async_sessionmaker[AsyncSession], Depends(_session_factory)]


@router.post(
    "/auth/signup",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[MeOut],
    summary="Create an account and its first business; starts a session",
)
async def signup(
    request: Request,
    response: Response,
    data: SignupRequest,
    db: DbSession,
    settings: AppSettings,
    limiter: Limiter,
    client: Client,
) -> Envelope[MeOut]:
    me, token = await service.signup(db, settings, limiter, data, client)
    set_session_cookie(response, settings, token)
    return envelope(request, me)


@router.post("/auth/login", response_model=Envelope[MeOut], summary="Start a session")
async def login(
    request: Request,
    response: Response,
    data: LoginRequest,
    db: DbSession,
    factory: SessionFactory,
    settings: AppSettings,
    limiter: Limiter,
    client: Client,
) -> Envelope[MeOut]:
    me, token = await service.login(db, factory, settings, limiter, data, client)
    set_session_cookie(response, settings, token)
    return envelope(request, me)


@router.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="End the current session (idempotent)",
)
async def logout(
    db: DbSession, auth: OptionalAuth, settings: AppSettings, client: Client
) -> Response:
    if auth is not None:
        await service.logout(db, auth, client)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response, settings)
    return response


@router.get(
    "/me", response_model=Envelope[MeOut], summary="The signed-in user and their businesses"
)
async def me(request: Request, db: DbSession, auth: CurrentAuth) -> Envelope[MeOut]:
    return envelope(request, await service.describe_user(db, auth.user))


@router.patch("/me", response_model=Envelope[MeOut], summary="Update your profile")
async def update_me(
    request: Request, data: UpdateProfileRequest, db: DbSession, auth: CurrentAuth
) -> Envelope[MeOut]:
    return envelope(request, await service.update_profile(db, auth, data))


@router.post(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change your password; signs out all other sessions",
)
async def change_password(
    data: ChangePasswordRequest,
    db: DbSession,
    auth: CurrentAuth,
    settings: AppSettings,
    limiter: Limiter,
    client: Client,
) -> Response:
    token = await service.change_password(db, settings, limiter, auth, data, client)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    set_session_cookie(response, settings, token)
    return response
