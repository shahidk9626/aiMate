"""Authentication and current-user services (STAGE_2_DESIGN.md §4, §6, §8).

Route handlers stay thin: they parse input, call one function here, and set
or clear the cookie. All rules live here:

- Signup creates user + business + owner membership + session in one
  transaction, after setting app.user_id / app.tenant_id for RLS.
- Login answers unknown email, wrong password and disabled account with the
  same INVALID_CREDENTIALS error and the same amount of work (dummy hash).
  Failed attempts are audited in their own transaction so the record
  survives the failing request.
- Sessions are found via the auth_session_lookup() function (the user is not
  known yet), then read normally under RLS. Idle and absolute expiry are
  enforced on every request.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import AppError, AuthenticationError, ConflictError
from app.core.rate_limit import RateLimiter
from app.db.ids import uuid7
from app.db.tenant import set_current_user, set_tenant
from app.modules.audit import service as audit
from app.modules.identity import rate_limits
from app.modules.identity.models import AuthSession, User
from app.modules.identity.passwords import (
    hash_password_async,
    validate_password,
    verify_password_async,
)
from app.modules.identity.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    MembershipOut,
    MeOut,
    SignupRequest,
    UpdateProfileRequest,
    UserOut,
)
from app.modules.identity.tokens import hash_token, issue_token
from app.modules.tenancy.service import active_memberships, create_tenant_with_owner


class InvalidCredentialsError(AuthenticationError):
    code = "INVALID_CREDENTIALS"
    message = "Incorrect email or password."


class IncorrectCurrentPasswordError(AppError):
    status_code = 400
    code = "INCORRECT_CURRENT_PASSWORD"
    message = "Your current password is incorrect."


@dataclass(frozen=True)
class ClientInfo:
    ip: str | None
    user_agent: str | None

    @property
    def rate_key(self) -> str:
        return self.ip or "unknown"


@dataclass(frozen=True)
class AuthenticatedUser:
    user: User
    session: AuthSession


def _now() -> datetime:
    return datetime.now(UTC)


async def _start_session(
    db: AsyncSession, settings: Settings, user_id: uuid.UUID, client: ClientInfo
) -> str:
    token = issue_token()
    db.add(
        AuthSession(
            user_id=user_id,
            token_hash=token.digest,
            expires_at=_now() + timedelta(days=settings.session_absolute_days),
            user_agent=(client.user_agent or "")[:512] or None,
            ip=client.ip,
        )
    )
    await db.flush()
    return token.value


async def _user_id_by_email(db: AsyncSession, email: str) -> uuid.UUID | None:
    result = await db.execute(text("SELECT auth_user_id_by_email(:email)"), {"email": email})
    value = result.scalar_one()
    return value if isinstance(value, uuid.UUID) else None


async def describe_user(db: AsyncSession, user: User) -> MeOut:
    memberships = await active_memberships(db, user.id)
    return MeOut(
        user=UserOut(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            email_verified=user.email_verified_at is not None,
            created_at=user.created_at,
        ),
        memberships=[
            MembershipOut(
                tenant_id=tenant.id, tenant_name=tenant.name, tenant_slug=tenant.slug, role=role
            )
            for tenant, role in memberships
        ],
    )


# --- signup / login / logout ------------------------------------------------------------


async def signup(
    db: AsyncSession,
    settings: Settings,
    limiter: RateLimiter,
    data: SignupRequest,
    client: ClientInfo,
) -> tuple[MeOut, str]:
    await limiter.enforce(rate_limits.SIGNUP_PER_IP, client.rate_key)
    validate_password(data.password, email=data.email)
    if await _user_id_by_email(db, data.email) is not None:
        raise ConflictError("An account with this email already exists.", code="EMAIL_TAKEN")

    user_id, tenant_id = uuid7(), uuid7()
    await set_current_user(db, user_id)
    await set_tenant(db, tenant_id)

    user = User(
        id=user_id,
        email=data.email,
        password_hash=await hash_password_async(data.password),
        full_name=data.full_name,
        last_login_at=_now(),
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:  # registered concurrently between check and insert
        raise ConflictError(
            "An account with this email already exists.", code="EMAIL_TAKEN"
        ) from exc

    tenant = await create_tenant_with_owner(
        db,
        tenant_id=tenant_id,
        owner_user_id=user_id,
        name=data.business_name,
        timezone=data.timezone,
    )
    token = await _start_session(db, settings, user_id, client)
    await audit.record(
        db,
        "auth.signup",
        tenant_id=tenant.id,
        actor_user_id=user_id,
        resource_type="tenant",
        resource_id=tenant.id,
        ip=client.ip,
    )
    await db.refresh(user)
    return await describe_user(db, user), token


async def login(
    db: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    limiter: RateLimiter,
    data: LoginRequest,
    client: ClientInfo,
) -> tuple[MeOut, str]:
    await limiter.enforce(rate_limits.LOGIN_PER_IP, client.rate_key)
    await limiter.enforce(
        rate_limits.LOGIN_PER_IP_AND_EMAIL, f"{client.rate_key}|{data.email.strip()}"
    )

    user_id = await _user_id_by_email(db, data.email.strip())
    user: User | None = None
    if user_id is not None:
        await set_current_user(db, user_id)
        user = await db.get(User, user_id)

    # Always exactly one Argon2 verification, whether or not the user exists.
    result = await verify_password_async(user.password_hash if user else None, data.password)
    if user is None or not result.ok or not user.is_active:
        await audit.record_independently(
            session_factory,
            "auth.login_failed",
            actor_user_id=user.id if user else None,
            ip=client.ip,
        )
        raise InvalidCredentialsError()

    if result.needs_rehash:
        user.password_hash = await hash_password_async(data.password)
    user.last_login_at = _now()
    token = await _start_session(db, settings, user.id, client)
    await audit.record(db, "auth.login", actor_user_id=user.id, ip=client.ip)
    return await describe_user(db, user), token


async def logout(db: AsyncSession, auth: AuthenticatedUser, client: ClientInfo) -> None:
    auth.session.revoked_at = _now()
    await audit.record(db, "auth.logout", actor_user_id=auth.user.id, ip=client.ip)


# --- current user -------------------------------------------------------------------------


async def authenticate(
    db: AsyncSession, settings: Settings, token: str
) -> AuthenticatedUser | None:
    """Resolve a session cookie to its user, enforcing revocation and both expiries."""
    row = (
        await db.execute(
            text("SELECT session_id, user_id FROM auth_session_lookup(:token_hash)"),
            {"token_hash": hash_token(token)},
        )
    ).first()
    if row is None:  # unknown, revoked or past absolute expiry
        return None
    session_id, user_id = row
    await set_current_user(db, user_id)
    session = await db.get(AuthSession, session_id)
    user = await db.get(User, user_id)
    if session is None or user is None or not user.is_active:
        return None

    now = _now()
    if session.last_seen_at + timedelta(days=settings.session_idle_days) < now:
        return None
    if now - session.last_seen_at > timedelta(minutes=settings.session_touch_minutes):
        session.last_seen_at = now
    return AuthenticatedUser(user=user, session=session)


async def update_profile(
    db: AsyncSession, auth: AuthenticatedUser, data: UpdateProfileRequest
) -> MeOut:
    auth.user.full_name = data.full_name
    await db.flush()
    await db.refresh(auth.user)
    return await describe_user(db, auth.user)


async def change_password(
    db: AsyncSession,
    settings: Settings,
    limiter: RateLimiter,
    auth: AuthenticatedUser,
    data: ChangePasswordRequest,
    client: ClientInfo,
) -> str:
    """Returns a new session token; every existing session (including this one) is revoked."""
    await limiter.enforce(rate_limits.PASSWORD_CHANGE_PER_USER, str(auth.user.id))
    current = await verify_password_async(auth.user.password_hash, data.current_password)
    if not current.ok:
        raise IncorrectCurrentPasswordError()
    validate_password(data.new_password, email=auth.user.email)

    auth.user.password_hash = await hash_password_async(data.new_password)
    await db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == auth.user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    token = await _start_session(db, settings, auth.user.id, client)
    await audit.record(db, "auth.password_changed", actor_user_id=auth.user.id, ip=client.ip)
    return token


async def sessions_for_user(db: AsyncSession, user_id: uuid.UUID) -> list[AuthSession]:
    """Active sessions (used by tests now, a 'your devices' page later)."""
    rows = await db.scalars(
        select(AuthSession).where(
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > _now(),
        )
    )
    return list(rows)
