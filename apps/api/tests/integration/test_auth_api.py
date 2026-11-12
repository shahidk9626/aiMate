"""Authentication endpoints end to end: HTTP → services → PostgreSQL (RLS) + Redis."""

import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from redis import Redis

from app.core.config import Settings
from app.db.ids import uuid7
from app.db.session import DbSession
from app.db.tenant import set_current_user
from app.main import create_app
from app.modules.identity import service as identity_service
from app.modules.identity.models import User
from app.modules.identity.passwords import verify_password_async
from tests.integration.conftest import owner_connect

CSRF = {"X-Requested-With": "leadflow"}
PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def clear_rate_limits(integration_settings: Settings) -> None:
    # Redis db 15 is reserved for tests (see integration conftest).
    pw = integration_settings.redis_password
    Redis(
        host=integration_settings.redis_host,
        port=integration_settings.redis_port,
        db=integration_settings.redis_db,
        password=pw.get_secret_value() if pw else None,
    ).flushdb()


@pytest.fixture
def app(integration_settings: Settings) -> FastAPI:
    return create_app(integration_settings)


@pytest.fixture
def new_client(integration_settings: Settings) -> Iterator[Callable[[], TestClient]]:
    """Each call returns an independent browser (own cookie jar).

    Each browser also gets its own app instance: a TestClient runs the app on
    its own event loop, and an async connection pool must not be shared
    across loops. (A real server has one loop, so this is test-only.)
    """
    stack: list[TestClient] = []

    def factory() -> TestClient:
        client = TestClient(
            create_app(integration_settings), headers=CSRF, raise_server_exceptions=False
        )
        client.__enter__()
        stack.append(client)
        return client

    yield factory
    for client in stack:
        client.__exit__(None, None, None)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, headers=CSRF, raise_server_exceptions=False) as test_client:
        yield test_client


def unique_email(name: str = "user") -> str:
    return f"{name}.{uuid.uuid4().hex[:10]}@example.com"


def signup(client: TestClient, email: str | None = None, **overrides: Any) -> Any:
    body = {
        "email": email or unique_email(),
        "password": PASSWORD,
        "full_name": "Asha Verma",
        "business_name": "Acme Dental",
        "timezone": "Asia/Kolkata",
        **overrides,
    }
    return client.post("/api/v1/auth/signup", json=body)


def login(client: TestClient, email: str, password: str = PASSWORD) -> Any:
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


@contextmanager
def owner_sql(settings: Settings) -> Iterator[Any]:
    """Superuser connection (bypasses RLS) for arranging and inspecting state."""
    with owner_connect(settings) as conn:
        yield conn


def audit_actions(settings: Settings, user_id: str) -> list[str]:
    with owner_sql(settings) as conn:
        rows = conn.execute(
            "SELECT action FROM audit_logs WHERE actor_user_id = %s ORDER BY created_at", (user_id,)
        ).fetchall()
    return [row[0] for row in rows]


# --- signup ---------------------------------------------------------------------------


def test_signup_creates_user_business_owner_and_session(
    client: TestClient, integration_settings: Settings
) -> None:
    email = unique_email("owner")
    response = signup(client, email)

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["user"]["email"] == email
    assert data["user"]["full_name"] == "Asha Verma"
    assert data["user"]["email_verified"] is False
    assert "password" not in response.text and "password_hash" not in response.text
    [membership] = data["memberships"]
    assert membership["role"] == "owner"
    assert membership["tenant_name"] == "Acme Dental"
    assert membership["tenant_slug"].startswith("acme-dental-")

    cookie = response.headers["set-cookie"]
    assert cookie.startswith("lf_session=") and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert client.get("/api/v1/me").json()["data"]["user"]["email"] == email

    with owner_sql(integration_settings) as conn:
        stored = conn.execute(
            "SELECT password_hash, (SELECT timezone FROM tenants WHERE id = %s) FROM users "
            "WHERE email = %s",
            (membership["tenant_id"], email),
        ).fetchone()
    assert stored is not None
    assert stored[0].startswith("$argon2id$")
    assert stored[1] == "Asia/Kolkata"
    assert audit_actions(integration_settings, data["user"]["id"]) == ["auth.signup"]


def test_signup_rejects_an_already_registered_email_case_insensitively(
    client: TestClient,
) -> None:
    email = unique_email("dup")
    assert signup(client, email).status_code == 201

    response = signup(client, email.upper())

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_TAKEN"


@pytest.mark.parametrize(
    ("overrides", "code", "field"),
    [
        ({"email": "not-an-email"}, "VALIDATION_ERROR", "body.email"),
        ({"full_name": "   "}, "VALIDATION_ERROR", "body.full_name"),
        ({"timezone": "Mars/Olympus"}, "VALIDATION_ERROR", "body.timezone"),
        ({"is_platform_admin": True}, "VALIDATION_ERROR", "body.is_platform_admin"),
        ({"password": "short"}, "PASSWORD_POLICY", "password"),
    ],
)
def test_signup_validation(
    client: TestClient, overrides: dict[str, Any], code: str, field: str
) -> None:
    response = signup(client, **overrides)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == code
    assert field in [d["field"] for d in error["details"]]
    assert "short" not in response.text  # submitted values are never echoed


def test_signup_password_must_not_equal_email(client: TestClient) -> None:
    email = unique_email("same")

    response = signup(client, email, password=email)

    assert response.json()["error"]["code"] == "PASSWORD_POLICY"


def test_signup_requires_csrf_header(app: FastAPI) -> None:
    with TestClient(app) as bare:
        response = bare.post("/api/v1/auth/signup", json={})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_REJECTED"


def test_signup_is_rate_limited_per_ip(client: TestClient) -> None:
    statuses = [signup(client).status_code for _ in range(6)]

    assert statuses == [201] * 5 + [429]


# --- login ------------------------------------------------------------------------------


def test_login_starts_a_new_session(new_client: Callable[[], TestClient]) -> None:
    email = unique_email("login")
    signup(new_client(), email)
    browser = new_client()

    response = login(browser, email.upper())

    assert response.status_code == 200
    assert response.json()["data"]["user"]["email"] == email
    assert browser.get("/api/v1/me").status_code == 200


def test_wrong_password_and_unknown_email_are_indistinguishable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    email = unique_email("known")
    signup(client, email)
    calls: list[bool] = []

    async def counting_verify(stored: str | None, password: str) -> Any:
        calls.append(stored is None)
        return await verify_password_async(stored, password)

    monkeypatch.setattr(identity_service, "verify_password_async", counting_verify)

    wrong = login(client, email, "wrong password!!")
    unknown = login(client, unique_email("nobody"), "wrong password!!")

    for response in (wrong, unknown):
        assert response.status_code == 401
        assert response.json()["error"] == {
            "code": "INVALID_CREDENTIALS",
            "message": "Incorrect email or password.",
            "details": [],
        }
        assert "set-cookie" not in response.headers
    # One full Argon2 verification each: a real hash, then the dummy one.
    assert calls == [False, True]


def test_failed_login_is_audited_even_though_the_request_fails(
    client: TestClient, integration_settings: Settings
) -> None:
    email = unique_email("audited")
    user_id = signup(client, email).json()["data"]["user"]["id"]

    login(client, email, "wrong password!!")

    assert audit_actions(integration_settings, user_id) == ["auth.signup", "auth.login_failed"]


def test_deactivated_user_cannot_log_in(client: TestClient, integration_settings: Settings) -> None:
    email = unique_email("disabled")
    signup(client, email)
    with owner_sql(integration_settings) as conn:
        conn.execute("UPDATE users SET is_active = false WHERE email = %s", (email,))

    response = login(client, email)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert client.get("/api/v1/me").status_code == 401  # existing session also stops working


def test_login_is_rate_limited_per_ip_and_email(client: TestClient) -> None:
    email = unique_email("limited")
    signup(client, email)

    statuses = [login(client, email, "wrong password!!").status_code for _ in range(6)]

    assert statuses == [401] * 5 + [429]
    blocked = login(client, email)  # even the right password waits for the window
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1
    assert login(client, unique_email("other")).status_code == 401  # other emails unaffected


# --- session ------------------------------------------------------------------------------


def test_me_requires_a_valid_session(client: TestClient) -> None:
    assert client.get("/api/v1/me").json()["error"]["code"] == "UNAUTHENTICATED"
    client.cookies.set("lf_session", "forged-token-value")
    assert client.get("/api/v1/me").status_code == 401


def test_logout_revokes_the_session_server_side(
    client: TestClient, integration_settings: Settings
) -> None:
    signup(client)
    token = client.cookies.get("lf_session")

    response = client.post("/api/v1/auth/logout")

    assert response.status_code == 204
    assert 'lf_session=""' in response.headers["set-cookie"]
    client.cookies.set("lf_session", token or "")  # replaying the old cookie must fail
    assert client.get("/api/v1/me").status_code == 401


def test_logout_without_a_session_is_harmless(client: TestClient) -> None:
    assert client.post("/api/v1/auth/logout").status_code == 204


def _set_session_times(settings: Settings, email: str, column: str, interval: str) -> None:
    with owner_sql(settings) as conn:
        conn.execute(
            f"UPDATE auth_sessions SET {column} = now() - interval '{interval}' "
            "WHERE user_id = (SELECT id FROM users WHERE email = %s)",
            (email,),
        )


def test_idle_sessions_expire(client: TestClient, integration_settings: Settings) -> None:
    email = unique_email("idle")
    signup(client, email)
    _set_session_times(integration_settings, email, "last_seen_at", "8 days")

    assert client.get("/api/v1/me").status_code == 401


def test_sessions_expire_absolutely_even_when_active(
    client: TestClient, integration_settings: Settings
) -> None:
    email = unique_email("absolute")
    signup(client, email)
    _set_session_times(integration_settings, email, "expires_at", "1 second")

    assert client.get("/api/v1/me").status_code == 401


def test_activity_refreshes_last_seen_at(
    client: TestClient, integration_settings: Settings
) -> None:
    email = unique_email("touch")
    signup(client, email)
    _set_session_times(integration_settings, email, "last_seen_at", "10 minutes")

    assert client.get("/api/v1/me").status_code == 200

    with owner_sql(integration_settings) as conn:
        row = conn.execute(
            "SELECT now() - last_seen_at < interval '1 minute' FROM auth_sessions "
            "WHERE user_id = (SELECT id FROM users WHERE email = %s)",
            (email,),
        ).fetchone()
    assert row == (True,)


# --- profile and password -------------------------------------------------------------------


def test_update_profile(client: TestClient) -> None:
    signup(client)

    response = client.patch("/api/v1/me", json={"full_name": "  Asha   K  Verma "})

    assert response.status_code == 200
    assert response.json()["data"]["user"]["full_name"] == "Asha K Verma"


def test_change_password_rotates_and_revokes_every_session(
    new_client: Callable[[], TestClient], integration_settings: Settings
) -> None:
    email = unique_email("rotate")
    laptop = new_client()
    signup(laptop, email)
    phone = new_client()
    login(phone, email)
    old_laptop_token = laptop.cookies.get("lf_session")

    response = laptop.post(
        "/api/v1/me/password",
        json={"current_password": PASSWORD, "new_password": "a brand new passphrase"},
    )

    assert response.status_code == 204
    assert laptop.cookies.get("lf_session") != old_laptop_token  # rotated
    assert laptop.get("/api/v1/me").status_code == 200
    assert phone.get("/api/v1/me").status_code == 401  # other device signed out
    assert login(new_client(), email).status_code == 401  # old password gone
    assert login(new_client(), email, "a brand new passphrase").status_code == 200
    user_id = laptop.get("/api/v1/me").json()["data"]["user"]["id"]
    assert "auth.password_changed" in audit_actions(integration_settings, user_id)


def test_change_password_requires_the_current_password(client: TestClient) -> None:
    signup(client)

    response = client.post(
        "/api/v1/me/password",
        json={"current_password": "not my password", "new_password": "a brand new passphrase"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INCORRECT_CURRENT_PASSWORD"
    assert client.get("/api/v1/me").status_code == 200  # still signed in


# --- isolation --------------------------------------------------------------------------------


def test_users_see_only_their_own_account_and_businesses(
    new_client: Callable[[], TestClient],
) -> None:
    alice, bob = new_client(), new_client()
    signup(alice, unique_email("alice"), business_name="Alice Realty")
    signup(bob, unique_email("bob"), business_name="Bob Salon")

    alice_me = alice.get("/api/v1/me").json()["data"]
    bob_me = bob.get("/api/v1/me").json()["data"]

    assert [m["tenant_name"] for m in alice_me["memberships"]] == ["Alice Realty"]
    assert [m["tenant_name"] for m in bob_me["memberships"]] == ["Bob Salon"]
    assert alice_me["user"]["id"] != bob_me["user"]["id"]


# --- transaction safety (regression for the DbSession commit timing) ----------------------------


def test_a_failed_commit_never_reports_success(app: FastAPI, client: TestClient) -> None:
    email = unique_email("race")
    signup(client, email)

    @app.post("/api/v1/_test/commit-fails", status_code=201)
    async def commit_fails(db: DbSession, response: Response) -> dict[str, bool]:
        user_id = uuid7()
        await set_current_user(db, user_id)
        # Not flushed: the unique violation surfaces only at commit time.
        db.add(User(id=user_id, email=email, password_hash="x", full_name="Duplicate"))
        response.set_cookie("probe", "1")
        return {"ok": True}

    response = client.post("/api/v1/_test/commit-fails")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "probe" not in response.headers.get("set-cookie", "")
