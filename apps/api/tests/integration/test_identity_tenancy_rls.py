"""Database-level isolation for the Stage 2 tables (ADR-023).

Everything runs through the restricted app role, exactly as the API will.
World: business A (Alice owner, Carol agent) and business B (Bob owner,
Carol admin). Carol belongs to both.
"""

import hashlib
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from sqlalchemy import Engine, insert, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.engine import create_sync_db_engine, sync_session_factory
from app.db.ids import uuid7
from app.db.tenant import set_current_user_sync, set_tenant_sync
from app.modules.audit.models import AuditLog
from app.modules.identity.models import AuthSession, EmailToken, EmailTokenPurpose, User
from app.modules.tenancy.models import Invitation, Membership, Role, Tenant
from tests.integration.conftest import owner_connect

NOW = datetime.now(UTC)
RUN = uuid.uuid4().hex[:8]  # keeps emails/slugs unique if the DB is reused


@dataclass(frozen=True)
class World:
    alice: uuid.UUID
    bob: uuid.UUID
    carol: uuid.UUID
    tenant_a: uuid.UUID
    tenant_b: uuid.UUID


def _token() -> bytes:
    return hashlib.sha256(os.urandom(32)).digest()


def _email(name: str) -> str:
    return f"{name}.{RUN}@example.com"


@contextmanager
def tx(
    engine: Engine, *, user: uuid.UUID | None = None, tenant: uuid.UUID | None = None
) -> Iterator[Session]:
    with sync_session_factory(engine).begin() as session:
        if user is not None:
            set_current_user_sync(session, user)
        if tenant is not None:
            set_tenant_sync(session, tenant)
        yield session


def _signup(engine: Engine, name: str, business: str) -> tuple[uuid.UUID, uuid.UUID]:
    """What the signup endpoint will do: user + tenant + owner membership."""
    user_id, tenant_id = uuid7(), uuid7()
    with tx(engine, user=user_id, tenant=tenant_id) as s:
        s.add(User(id=user_id, email=_email(name), password_hash="x", full_name=name))
        s.flush()
        s.add(Tenant(id=tenant_id, name=business, slug=f"{business}-{RUN}"))
        s.flush()
        s.add(Membership(tenant_id=tenant_id, user_id=user_id, role=Role.OWNER))
    return user_id, tenant_id


def _assert_rls_violation(exc: DBAPIError) -> None:
    assert isinstance(exc.orig, psycopg.errors.InsufficientPrivilege)
    assert "row-level security" in str(exc.orig)


def _assert_permission_denied(exc: DBAPIError) -> None:
    assert isinstance(exc.orig, psycopg.errors.InsufficientPrivilege)
    assert "permission denied" in str(exc.orig)


@pytest.fixture(scope="module")
def engine(integration_settings: Settings) -> Iterator[Engine]:
    engine = create_sync_db_engine(integration_settings)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def world(engine: Engine) -> World:
    alice, tenant_a = _signup(engine, "alice", "acme")
    bob, tenant_b = _signup(engine, "bob", "bobco")
    carol = uuid7()
    with tx(engine, user=carol) as s:
        s.add(User(id=carol, email=_email("carol"), password_hash="x", full_name="Carol"))
    with tx(engine, tenant=tenant_a) as s:
        s.add(Membership(tenant_id=tenant_a, user_id=carol, role=Role.AGENT))
    with tx(engine, tenant=tenant_b) as s:
        s.add(Membership(tenant_id=tenant_b, user_id=carol, role=Role.ADMIN))
    return World(alice, bob, carol, tenant_a, tenant_b)


def _ids(session: Session, model: type[User] | type[Tenant]) -> set[uuid.UUID]:
    return set(session.scalars(select(model.id)))


# --- coverage ---------------------------------------------------------------


def test_every_table_has_forced_rls_except_documented_exceptions(
    integration_settings: Settings, world: World
) -> None:
    exceptions = {"alembic_version", "outbox_events"}
    with owner_connect(integration_settings) as conn:
        rows = conn.execute(
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relnamespace = 'public'::regnamespace AND relkind = 'r'"
        ).fetchall()

    missing = [
        name for name, rls, forced in rows if name not in exceptions and not (rls and forced)
    ]
    assert missing == []


# --- visibility ---------------------------------------------------------------


def test_no_identity_sees_nothing(engine: Engine, world: World) -> None:
    with tx(engine) as s:
        for table in (
            "users",
            "tenants",
            "memberships",
            "invitations",
            "auth_sessions",
            "email_tokens",
            "audit_logs",
        ):
            assert s.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0, table


def test_user_sees_only_own_user_row_and_own_businesses(engine: Engine, world: World) -> None:
    with tx(engine, user=world.alice) as s:
        assert _ids(s, User) == {world.alice}
        assert _ids(s, Tenant) == {world.tenant_a}
        memberships = s.execute(select(Membership.tenant_id, Membership.user_id)).all()
        assert memberships == [(world.tenant_a, world.alice)]


def test_member_of_two_businesses_sees_both(engine: Engine, world: World) -> None:
    with tx(engine, user=world.carol) as s:
        assert _ids(s, Tenant) == {world.tenant_a, world.tenant_b}
        assert set(s.scalars(select(Membership.tenant_id))) == {world.tenant_a, world.tenant_b}


def test_tenant_context_shows_teammates_but_not_other_businesses_users(
    engine: Engine, world: World
) -> None:
    with tx(engine, user=world.alice, tenant=world.tenant_a) as s:
        assert _ids(s, User) == {world.alice, world.carol}
        assert set(s.scalars(select(Membership.tenant_id))) == {world.tenant_a}


def test_disabled_membership_does_not_reveal_the_business(engine: Engine, world: World) -> None:
    user_id = uuid7()
    with tx(engine, user=user_id) as s:
        s.add(User(id=user_id, email=_email("dave"), password_hash="x", full_name="Dave"))
    with tx(engine, tenant=world.tenant_b) as s:
        s.add(
            Membership(
                tenant_id=world.tenant_b, user_id=user_id, role=Role.AGENT, status="disabled"
            )
        )
    with tx(engine, user=user_id) as s:
        assert _ids(s, Tenant) == set()


# --- writes -------------------------------------------------------------------


def test_cannot_create_a_user_row_for_someone_else(engine: Engine, world: World) -> None:
    with pytest.raises(DBAPIError) as exc_info, tx(engine, user=world.alice) as s:
        s.add(User(id=uuid7(), email=_email("mallory"), password_hash="x", full_name="M"))
        s.flush()
    _assert_rls_violation(exc_info.value)


def test_cannot_update_another_users_row(engine: Engine, world: World) -> None:
    with tx(engine, user=world.alice, tenant=world.tenant_a) as s:
        # Carol is visible as a teammate, but only her own session may change her row.
        result = s.execute(
            text("UPDATE users SET full_name = 'hacked' WHERE id = :id"), {"id": world.carol}
        )
    assert result.rowcount == 0  # type: ignore[attr-defined]


def test_cannot_add_membership_to_another_business(engine: Engine, world: World) -> None:
    with (
        pytest.raises(DBAPIError) as exc_info,
        tx(engine, user=world.alice, tenant=world.tenant_a) as s,
    ):
        s.add(Membership(tenant_id=world.tenant_b, user_id=world.alice, role=Role.OWNER))
        s.flush()
    _assert_rls_violation(exc_info.value)


def test_cannot_update_another_business(engine: Engine, world: World) -> None:
    with tx(engine, user=world.alice, tenant=world.tenant_a) as s:
        result = s.execute(
            text("UPDATE tenants SET name = 'hacked' WHERE id = :id"), {"id": world.tenant_b}
        )
    assert result.rowcount == 0  # type: ignore[attr-defined]
    with tx(engine, user=world.bob) as s:
        assert s.get(Tenant, world.tenant_b).name == "bobco"  # type: ignore[union-attr]


def test_cannot_remove_members_of_another_business(engine: Engine, world: World) -> None:
    with tx(engine, user=world.carol, tenant=world.tenant_a) as s:
        # Carol can see her own B membership, but cannot delete rows outside tenant A.
        result = s.execute(
            text("DELETE FROM memberships WHERE tenant_id = :b"), {"b": world.tenant_b}
        )
    assert result.rowcount == 0  # type: ignore[attr-defined]


@pytest.mark.parametrize("table", ["tenants", "users"])
def test_app_role_cannot_delete_tenants_or_users(engine: Engine, world: World, table: str) -> None:
    with (
        pytest.raises(DBAPIError) as exc_info,
        tx(engine, user=world.alice, tenant=world.tenant_a) as s,
    ):
        s.execute(text(f"DELETE FROM {table} WHERE id = :id"), {"id": world.alice})
    _assert_permission_denied(exc_info.value)


# --- sessions and tokens ------------------------------------------------------------


def test_sessions_and_tokens_are_visible_only_to_their_user(engine: Engine, world: World) -> None:
    with tx(engine, user=world.alice) as s:
        s.add(
            AuthSession(
                user_id=world.alice, token_hash=_token(), expires_at=NOW + timedelta(days=1)
            )
        )
        s.add(
            EmailToken(
                user_id=world.alice,
                purpose=EmailTokenPurpose.PASSWORD_RESET,
                token_hash=_token(),
                expires_at=NOW + timedelta(hours=1),
            )
        )
    with tx(engine, user=world.bob, tenant=world.tenant_b) as s:
        assert s.execute(select(AuthSession)).all() == []
        assert s.execute(select(EmailToken)).all() == []
    with tx(engine, user=world.alice) as s:
        assert len(s.execute(select(AuthSession)).all()) == 1


def test_cannot_create_a_session_for_another_user(engine: Engine, world: World) -> None:
    with pytest.raises(DBAPIError) as exc_info, tx(engine, user=world.alice) as s:
        s.add(
            AuthSession(user_id=world.bob, token_hash=_token(), expires_at=NOW + timedelta(days=1))
        )
        s.flush()
    _assert_rls_violation(exc_info.value)


# --- audit log ------------------------------------------------------------------------


def _audit(session: Session, tenant: uuid.UUID | None, action: str) -> None:
    # Core insert without RETURNING (see AuditLog docstring).
    session.execute(insert(AuditLog).values(id=uuid7(), tenant_id=tenant, action=action))


def test_audit_log_scoping(engine: Engine, world: World) -> None:
    with tx(engine) as s:
        _audit(s, None, "auth.login_failed")  # no identity yet, no tenant: allowed
    with tx(engine, user=world.alice, tenant=world.tenant_a) as s:
        _audit(s, world.tenant_a, "tenant.updated")
    with tx(engine, user=world.bob, tenant=world.tenant_b) as s:
        _audit(s, world.tenant_b, "tenant.updated")

    with tx(engine, user=world.alice, tenant=world.tenant_a) as s:
        visible = set(s.scalars(select(AuditLog.tenant_id)))
    assert visible == {world.tenant_a}


def test_audit_log_cannot_be_written_for_another_business(engine: Engine, world: World) -> None:
    with (
        pytest.raises(DBAPIError) as exc_info,
        tx(engine, user=world.alice, tenant=world.tenant_a) as s,
    ):
        _audit(s, world.tenant_b, "forged")
    _assert_rls_violation(exc_info.value)


@pytest.mark.parametrize(
    "statement", ["UPDATE audit_logs SET action = 'x'", "DELETE FROM audit_logs"]
)
def test_audit_log_is_append_only(engine: Engine, world: World, statement: str) -> None:
    with (
        pytest.raises(DBAPIError) as exc_info,
        tx(engine, user=world.alice, tenant=world.tenant_a) as s,
    ):
        s.execute(text(statement))
    _assert_permission_denied(exc_info.value)


# --- invitations ------------------------------------------------------------------------


def _invite(engine: Engine, tenant: uuid.UUID, email: str, **extra: object) -> uuid.UUID:
    invitation_id = uuid7()
    with tx(engine, tenant=tenant) as s:
        s.add(
            Invitation(
                id=invitation_id,
                tenant_id=tenant,
                email=email,
                role=Role.AGENT,
                token_hash=extra.pop("token_hash", _token()),
                expires_at=extra.pop("expires_at", NOW + timedelta(days=7)),
                **extra,
            )
        )
    return invitation_id


def test_invitations_are_tenant_isolated(engine: Engine, world: World) -> None:
    invitation_id = _invite(engine, world.tenant_a, _email("newhire"))

    with tx(engine, user=world.bob, tenant=world.tenant_b) as s:
        assert s.get(Invitation, invitation_id) is None
    with tx(engine, user=world.alice, tenant=world.tenant_a) as s:
        assert s.get(Invitation, invitation_id) is not None


def test_only_one_open_invitation_per_email_per_business(engine: Engine, world: World) -> None:
    email = _email("twice")
    first = _invite(engine, world.tenant_a, email)
    with pytest.raises(IntegrityError):
        _invite(engine, world.tenant_a, email)

    _invite(engine, world.tenant_b, email)  # another business may invite the same person
    with tx(engine, tenant=world.tenant_a) as s:
        s.execute(text("UPDATE invitations SET revoked_at = now() WHERE id = :id"), {"id": first})
    _invite(engine, world.tenant_a, email)  # allowed again once the first is closed


# --- pre-tenant lookup functions ----------------------------------------------------------


def test_user_lookup_by_email_is_case_insensitive_and_returns_only_the_id(
    engine: Engine, world: World
) -> None:
    with tx(engine) as s:
        found = s.execute(
            text("SELECT * FROM auth_user_id_by_email(:e)"), {"e": _email("alice").upper()}
        ).all()
        missing = s.execute(
            text("SELECT auth_user_id_by_email(:e)"), {"e": _email("nobody")}
        ).scalar_one()
    assert found == [(world.alice,)]
    assert missing is None


def test_session_lookup_ignores_revoked_and_expired_sessions(engine: Engine, world: World) -> None:
    valid, revoked, expired = _token(), _token(), _token()
    with tx(engine, user=world.bob) as s:
        s.add(AuthSession(user_id=world.bob, token_hash=valid, expires_at=NOW + timedelta(days=1)))
        s.add(
            AuthSession(
                user_id=world.bob,
                token_hash=revoked,
                expires_at=NOW + timedelta(days=1),
                revoked_at=NOW,
            )
        )
        s.add(
            AuthSession(
                user_id=world.bob, token_hash=expired, expires_at=NOW - timedelta(seconds=1)
            )
        )

    with tx(engine) as s:

        def lookup(token: bytes) -> list[tuple[object, ...]]:
            rows = s.execute(text("SELECT * FROM auth_session_lookup(:t)"), {"t": token}).all()
            return [tuple(row) for row in rows]

        result = lookup(valid)
        assert len(result) == 1 and result[0][1] == world.bob
        assert lookup(revoked) == []
        assert lookup(expired) == []
        assert lookup(_token()) == []


def test_email_token_lookup_checks_purpose_and_single_use(engine: Engine, world: World) -> None:
    token = _token()
    with tx(engine, user=world.carol) as s:
        s.add(
            EmailToken(
                user_id=world.carol,
                purpose=EmailTokenPurpose.PASSWORD_RESET,
                token_hash=token,
                expires_at=NOW + timedelta(hours=1),
            )
        )

    query = text("SELECT user_id FROM email_token_lookup(:t, :p)")
    with tx(engine) as s:
        assert s.execute(query, {"t": token, "p": "password_reset"}).scalars().all() == [
            world.carol
        ]
        assert s.execute(query, {"t": token, "p": "email_verification"}).all() == []

    with tx(engine, user=world.carol) as s:
        s.execute(
            text("UPDATE email_tokens SET used_at = now() WHERE token_hash = :t"), {"t": token}
        )
    with tx(engine) as s:
        assert s.execute(query, {"t": token, "p": "password_reset"}).all() == []


def test_invitation_lookup_returns_ids_for_open_invitations_only(
    engine: Engine, world: World
) -> None:
    open_token, expired_token = _token(), _token()
    open_id = _invite(engine, world.tenant_b, _email("lookup-open"), token_hash=open_token)
    _invite(
        engine,
        world.tenant_b,
        _email("lookup-expired"),
        token_hash=expired_token,
        expires_at=NOW - timedelta(seconds=1),
    )

    query = text("SELECT * FROM invitation_lookup(:t)")
    with tx(engine) as s:
        assert [tuple(r) for r in s.execute(query, {"t": open_token})] == [
            (open_id, world.tenant_b)
        ]
        assert s.execute(query, {"t": expired_token}).all() == []


# --- lookup role boundaries -----------------------------------------------------------------


def test_lookup_role_is_locked_down(integration_settings: Settings, world: World) -> None:
    lookup, app = integration_settings.db_lookup_role, integration_settings.app_db_user
    with owner_connect(integration_settings) as conn:
        role = conn.execute(
            "SELECT rolcanlogin, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = %s", (lookup,)
        ).fetchone()
        checks = conn.execute(
            "SELECT has_column_privilege(%(l)s, 'users', 'password_hash', 'SELECT'), "
            "has_table_privilege(%(l)s, 'tenants', 'SELECT'), "
            "has_schema_privilege(%(l)s, 'public', 'CREATE'), "
            "pg_has_role(%(a)s, %(l)s, 'MEMBER'), "
            "has_function_privilege('public', 'auth_user_id_by_email(citext)', 'EXECUTE')",
            {"l": lookup, "a": app},
        ).fetchone()
    assert role == (False, False, False)
    # Cannot read password hashes or tenants, cannot create objects, the app
    # role cannot become it, and PUBLIC cannot call the functions.
    assert checks == (False, False, False, False, False)


def test_invalid_role_rejected_by_database_check(engine: Engine, world: World) -> None:
    with pytest.raises(IntegrityError), tx(engine, tenant=world.tenant_a) as s:
        s.execute(
            text(
                "INSERT INTO memberships (id, tenant_id, user_id, role) "
                "VALUES (:id, :t, :u, 'superadmin')"
            ),
            {"id": uuid7(), "t": world.tenant_a, "u": world.bob},
        )
