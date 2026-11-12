"""Tenant context, business profile and team management over HTTP.

Users, sessions, businesses and memberships are arranged directly in the
database (owner connection) so each test can build exactly the team it needs
without paying for Argon2 hashing; every check then goes through the API.
"""

import contextlib
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import anyio
import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.engine import async_session_factory, create_async_db_engine
from app.db.ids import uuid7
from app.db.tenant import set_current_user, set_tenant
from app.main import create_app
from app.modules.identity.tokens import issue_token
from app.modules.tenancy.context import TenantContext
from app.modules.tenancy.models import Role
from app.modules.tenancy.schemas import UpdateMemberRequest
from app.modules.tenancy.service import LastOwnerError, change_member_role
from tests.integration.conftest import owner_connect

CSRF = {"X-Requested-With": "leadflow"}


@dataclass(frozen=True)
class Person:
    id: uuid.UUID
    email: str
    token: str


@dataclass(frozen=True)
class Team:
    tenant: uuid.UUID
    owner: Person
    owner2: Person
    admin: Person
    admin2: Person
    agent: Person
    agent2: Person


@pytest.fixture
def db(integration_settings: Settings) -> Iterator[psycopg.Connection]:
    with owner_connect(integration_settings) as conn:
        yield conn


@pytest.fixture
def app(integration_settings: Settings) -> FastAPI:
    return create_app(integration_settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, headers=CSRF, raise_server_exceptions=False) as test_client:
        yield test_client


def make_user(db: psycopg.Connection, name: str) -> Person:
    user_id = uuid7()
    email = f"{name}.{uuid.uuid4().hex[:8]}@example.com"
    db.execute(
        "INSERT INTO users (id, email, password_hash, full_name) VALUES (%s, %s, 'x', %s)",
        (user_id, email, name.title()),
    )
    token = issue_token()
    db.execute(
        "INSERT INTO auth_sessions (id, user_id, token_hash, expires_at) "
        "VALUES (%s, %s, %s, now() + interval '1 day')",
        (uuid7(), user_id, token.digest),
    )
    return Person(user_id, email, token.value)


def make_tenant(db: psycopg.Connection, name: str, status: str = "active") -> uuid.UUID:
    tenant_id = uuid7()
    db.execute(
        "INSERT INTO tenants (id, name, slug, status) VALUES (%s, %s, %s, %s)",
        (tenant_id, name, f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}", status),
    )
    return tenant_id


def add_member(
    db: psycopg.Connection, tenant: uuid.UUID, person: Person, role: str, status: str = "active"
) -> None:
    db.execute(
        "INSERT INTO memberships (id, tenant_id, user_id, role, status) "
        "VALUES (%s, %s, %s, %s, %s)",
        (uuid7(), tenant, person.id, role, status),
    )


def make_team(db: psycopg.Connection, name: str = "Acme Dental", owners: int = 2) -> Team:
    tenant = make_tenant(db, name)
    people = {
        role: make_user(db, role)
        for role in ("owner", "owner2", "admin", "admin2", "agent", "agent2")
    }
    for key, person in people.items():
        role = key.rstrip("2")
        if key == "owner2" and owners < 2:
            role = "admin"
        add_member(db, tenant, person, role)
    return Team(tenant=tenant, **people)


def as_(person: Person, tenant: uuid.UUID | str | None) -> dict[str, str]:
    headers = {"Cookie": f"lf_session={person.token}"}
    if tenant is not None:
        headers["X-Tenant-ID"] = str(tenant)
    return headers


def member_roles(client: TestClient, viewer: Person, tenant: uuid.UUID) -> dict[str, str]:
    body = client.get("/api/v1/tenant/members", headers=as_(viewer, tenant)).json()
    return {m["email"]: m["role"] for m in body["data"]}


# --- tenant context ---------------------------------------------------------------------


def test_tenant_header_is_required_and_must_be_a_uuid(
    client: TestClient, db: psycopg.Connection
) -> None:
    team = make_team(db)

    missing = client.get("/api/v1/tenant", headers=as_(team.owner, None))
    malformed = client.get("/api/v1/tenant", headers=as_(team.owner, "acme"))

    assert (missing.status_code, missing.json()["error"]["code"]) == (400, "TENANT_REQUIRED")
    assert (malformed.status_code, malformed.json()["error"]["code"]) == (400, "INVALID_TENANT_ID")


def test_tenant_routes_require_a_session(client: TestClient, db: psycopg.Connection) -> None:
    team = make_team(db)

    response = client.get("/api/v1/tenant", headers={"X-Tenant-ID": str(team.tenant)})

    assert response.status_code == 401


def test_other_and_nonexistent_businesses_look_identical(
    client: TestClient, db: psycopg.Connection
) -> None:
    mine, theirs = make_team(db, "Mine"), make_team(db, "Theirs")

    foreign = client.get("/api/v1/tenant", headers=as_(mine.owner, theirs.tenant))
    missing = client.get("/api/v1/tenant", headers=as_(mine.owner, uuid7()))

    for response in (foreign, missing):
        assert response.status_code == 404
        assert response.json()["error"] == {
            "code": "TENANT_NOT_FOUND",
            "message": "Business not found.",
            "details": [],
        }
    denied = db.execute(
        "SELECT count(*) FROM audit_logs WHERE action = 'security.tenant_access_denied' "
        "AND actor_user_id = %s",
        (mine.owner.id,),
    ).fetchone()
    assert denied == (2,)


def test_disabled_membership_has_no_access(client: TestClient, db: psycopg.Connection) -> None:
    team = make_team(db)
    db.execute("UPDATE memberships SET status = 'disabled' WHERE user_id = %s", (team.agent.id,))

    response = client.get("/api/v1/tenant", headers=as_(team.agent, team.tenant))

    assert response.status_code == 404


@pytest.mark.parametrize("status", ["suspended", "cancelled"])
def test_inactive_business_is_blocked(
    client: TestClient, db: psycopg.Connection, status: str
) -> None:
    team = make_team(db)
    db.execute("UPDATE tenants SET status = %s WHERE id = %s", (status, team.tenant))

    response = client.get("/api/v1/tenant", headers=as_(team.owner, team.tenant))

    assert (response.status_code, response.json()["error"]["code"]) == (403, "TENANT_INACTIVE")


def test_member_of_two_businesses_switches_with_the_header(
    client: TestClient, db: psycopg.Connection
) -> None:
    clinic, agency = make_team(db, "Clinic"), make_team(db, "Agency")
    carol = make_user(db, "carol")
    add_member(db, clinic.tenant, carol, "agent")
    add_member(db, agency.tenant, carol, "admin")

    in_clinic = client.get("/api/v1/tenant", headers=as_(carol, clinic.tenant)).json()["data"]
    in_agency = client.get("/api/v1/tenant", headers=as_(carol, agency.tenant)).json()["data"]
    clinic_team = member_roles(client, carol, clinic.tenant)

    assert (in_clinic["name"], in_agency["name"]) == ("Clinic", "Agency")
    assert clinic.owner.email in clinic_team and agency.owner.email not in clinic_team
    assert clinic_team[carol.email] == "agent"
    assert member_roles(client, carol, agency.tenant)[carol.email] == "admin"


def test_cannot_touch_members_of_another_business(
    client: TestClient, db: psycopg.Connection
) -> None:
    mine, theirs = make_team(db, "Mine"), make_team(db, "Theirs")

    change = client.patch(
        f"/api/v1/tenant/members/{theirs.agent.id}",
        json={"role": "owner"},
        headers=as_(mine.owner, mine.tenant),
    )
    remove = client.delete(
        f"/api/v1/tenant/members/{theirs.agent.id}", headers=as_(mine.owner, mine.tenant)
    )

    for response in (change, remove):
        assert (response.status_code, response.json()["error"]["code"]) == (
            404,
            "MEMBER_NOT_FOUND",
        )
    assert member_roles(client, theirs.owner, theirs.tenant)[theirs.agent.email] == "agent"


# --- business profile -----------------------------------------------------------------------


@pytest.mark.parametrize(("actor", "expected"), [("owner", 200), ("admin", 200), ("agent", 403)])
def test_who_can_edit_the_business(
    client: TestClient, db: psycopg.Connection, actor: str, expected: int
) -> None:
    team = make_team(db)

    response = client.patch(
        "/api/v1/tenant",
        json={"name": "Acme Dental Clinic", "timezone": "Europe/London", "locale": "en-GB"},
        headers=as_(getattr(team, actor), team.tenant),
    )

    assert response.status_code == expected
    if expected == 200:
        data = response.json()["data"]
        assert (data["name"], data["timezone"], data["locale"]) == (
            "Acme Dental Clinic",
            "Europe/London",
            "en-GB",
        )
        row = db.execute(
            "SELECT metadata FROM audit_logs WHERE action = 'tenant.updated' AND tenant_id = %s",
            (team.tenant,),
        ).fetchone()
        assert row is not None and row[0] == {"fields": ["locale", "name", "timezone"]}
    else:
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.parametrize(
    "body",
    [{}, {"name": None}, {"timezone": "Nowhere/Land"}, {"locale": "english"}, {"slug": "x"}],
)
def test_business_update_validation(
    client: TestClient, db: psycopg.Connection, body: dict[str, Any]
) -> None:
    team = make_team(db)

    response = client.patch("/api/v1/tenant", json=body, headers=as_(team.owner, team.tenant))

    assert response.status_code == 422


def test_team_list_is_visible_to_every_member_and_ordered_by_role(
    client: TestClient, db: psycopg.Connection
) -> None:
    team = make_team(db)

    response = client.get("/api/v1/tenant/members", headers=as_(team.agent, team.tenant))

    assert response.status_code == 200
    roles = [m["role"] for m in response.json()["data"]]
    assert roles == ["owner", "owner", "admin", "admin", "agent", "agent"]
    assert set(response.json()["data"][0]) == {
        "user_id",
        "full_name",
        "email",
        "role",
        "status",
        "joined_at",
    }


# --- role matrix -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("actor", "target", "new_role", "expected"),
    [
        ("owner", "agent", "admin", 200),
        ("owner", "admin", "agent", 200),
        ("owner", "agent", "owner", 200),
        ("owner", "owner2", "admin", 200),  # another owner remains
        ("admin", "agent", "admin", 403),  # creating admins is owner-only
        ("admin", "agent2", "agent", 403),
        ("admin", "admin", "agent", 403),  # not even yourself
        ("agent", "agent2", "admin", 403),
        ("agent", "agent", "owner", 403),  # no self-promotion
    ],
)
def test_role_change_matrix(
    client: TestClient,
    db: psycopg.Connection,
    actor: str,
    target: str,
    new_role: str,
    expected: int,
) -> None:
    team = make_team(db)
    target_person: Person = getattr(team, target)

    response = client.patch(
        f"/api/v1/tenant/members/{target_person.id}",
        json={"role": new_role},
        headers=as_(getattr(team, actor), team.tenant),
    )

    assert response.status_code == expected
    roles = member_roles(client, team.owner, team.tenant)
    if expected == 200:
        assert response.json()["data"]["role"] == new_role
        assert roles[target_person.email] == new_role
    else:
        assert roles[target_person.email] == target.rstrip("2")


@pytest.mark.parametrize(
    ("actor", "target", "expected"),
    [
        ("owner", "owner2", 204),
        ("owner", "admin", 204),
        ("owner", "agent", 204),
        ("admin", "agent", 204),
        ("admin", "admin2", 403),
        ("admin", "owner", 403),
        ("agent", "agent2", 403),
        ("agent", "admin", 403),
        # leaving: anyone may remove themselves
        ("agent", "agent", 204),
        ("admin", "admin", 204),
        ("owner", "owner", 204),  # owner2 remains
    ],
)
def test_remove_member_matrix(
    client: TestClient, db: psycopg.Connection, actor: str, target: str, expected: int
) -> None:
    team = make_team(db)
    target_person: Person = getattr(team, target)

    response = client.delete(
        f"/api/v1/tenant/members/{target_person.id}",
        headers=as_(getattr(team, actor), team.tenant),
    )

    assert response.status_code == expected
    viewer = team.owner2 if target == "owner" else team.owner
    still_member = target_person.email in member_roles(client, viewer, team.tenant)
    assert still_member is (expected != 204)


def test_removed_member_loses_access_immediately(
    client: TestClient, db: psycopg.Connection
) -> None:
    team = make_team(db)
    assert client.get("/api/v1/tenant", headers=as_(team.agent, team.tenant)).status_code == 200

    client.delete(f"/api/v1/tenant/members/{team.agent.id}", headers=as_(team.owner, team.tenant))

    assert client.get("/api/v1/tenant", headers=as_(team.agent, team.tenant)).status_code == 404
    actions = db.execute(
        "SELECT action FROM audit_logs WHERE tenant_id = %s AND resource_id = %s",
        (team.tenant, team.agent.id),
    ).fetchall()
    assert actions == [("member.removed",)]


def test_unknown_role_is_rejected(client: TestClient, db: psycopg.Connection) -> None:
    team = make_team(db)

    response = client.patch(
        f"/api/v1/tenant/members/{team.agent.id}",
        json={"role": "superadmin"},
        headers=as_(team.owner, team.tenant),
    )

    assert response.status_code == 422


# --- last owner --------------------------------------------------------------------------------


def test_sole_owner_cannot_demote_themselves_or_leave(
    client: TestClient, db: psycopg.Connection
) -> None:
    team = make_team(db, owners=1)
    headers = as_(team.owner, team.tenant)

    demote = client.patch(
        f"/api/v1/tenant/members/{team.owner.id}", json={"role": "admin"}, headers=headers
    )
    leave = client.delete(f"/api/v1/tenant/members/{team.owner.id}", headers=headers)

    for response in (demote, leave):
        assert (response.status_code, response.json()["error"]["code"]) == (409, "LAST_OWNER")
    assert member_roles(client, team.owner, team.tenant)[team.owner.email] == "owner"


def test_owner_can_step_down_once_another_owner_exists(
    client: TestClient, db: psycopg.Connection
) -> None:
    team = make_team(db, owners=1)
    headers = as_(team.owner, team.tenant)

    promote = client.patch(
        f"/api/v1/tenant/members/{team.admin.id}", json={"role": "owner"}, headers=headers
    )
    step_down = client.patch(
        f"/api/v1/tenant/members/{team.owner.id}", json={"role": "admin"}, headers=headers
    )

    assert (promote.status_code, step_down.status_code) == (200, 200)
    roles = member_roles(client, team.admin, team.tenant)
    assert (roles[team.admin.email], roles[team.owner.email]) == ("owner", "admin")


@pytest.mark.anyio
async def test_two_owners_demoting_each_other_concurrently_keep_one_owner(
    integration_settings: Settings, db: psycopg.Connection
) -> None:
    """Owner rows are locked before counting, so the second demotion waits and then fails."""
    team = make_team(db)
    engine = create_async_db_engine(integration_settings)
    factory = async_session_factory(engine)
    first_holds_locks = anyio.Event()
    outcomes: dict[str, str] = {}

    async def demote(actor: Person, target: Person, label: str, hold: bool) -> None:
        async with factory() as session, session.begin():
            await set_current_user(session, actor.id)
            await set_tenant(session, team.tenant)
            ctx = TenantContext(team.tenant, actor.id, Role.OWNER)
            try:
                await change_member_role(
                    session, ctx, target.id, UpdateMemberRequest(role=Role.ADMIN), None
                )
                outcomes[label] = "ok"
            except LastOwnerError:
                outcomes[label] = "last_owner"
                raise
            if hold:
                first_holds_locks.set()
                await anyio.sleep(0.5)  # keep the transaction (and locks) open

    async def second() -> None:
        await first_holds_locks.wait()
        with contextlib.suppress(LastOwnerError):
            await demote(team.owner2, team.owner, "second", hold=False)

    try:
        async with anyio.create_task_group() as tg:
            tg.start_soon(demote, team.owner, team.owner2, "first", True)
            tg.start_soon(second)
    finally:
        await engine.dispose()

    assert outcomes == {"first": "ok", "second": "last_owner"}
    owners = db.execute(
        "SELECT count(*) FROM memberships WHERE tenant_id = %s AND role = 'owner'", (team.tenant,)
    ).fetchone()
    assert owners == (1,)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
