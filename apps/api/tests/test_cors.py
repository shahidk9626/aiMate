import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from app.core.config import Environment, Settings
from app.main import create_app

ALLOWED = "http://localhost:3000"


def _client(origin: str = ALLOWED) -> TestClient:
    settings = Settings(_env_file=None, app_env=Environment.TEST, web_origin=origin)
    return TestClient(create_app(settings))


def test_allowed_origin_gets_cors_headers_with_credentials() -> None:
    response = _client().get("/healthz", headers={"Origin": ALLOWED})

    assert response.headers["Access-Control-Allow-Origin"] == ALLOWED
    assert response.headers["Access-Control-Allow-Credentials"] == "true"
    assert "X-Request-ID" in response.headers["Access-Control-Expose-Headers"]


def test_other_origins_get_no_cors_headers() -> None:
    response = _client().get("/healthz", headers={"Origin": "https://evil.example"})

    assert response.status_code == 200  # CORS is enforced by the browser
    assert "Access-Control-Allow-Origin" not in response.headers


def test_preflight_allows_api_headers_for_trusted_origin() -> None:
    response = _client().options(
        "/api/v1/anything",
        headers={
            "Origin": ALLOWED,
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "content-type, x-tenant-id, idempotency-key",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == ALLOWED
    assert "PATCH" in response.headers["Access-Control-Allow-Methods"]


def test_preflight_rejected_for_untrusted_origin() -> None:
    response = _client().options(
        "/api/v1/anything",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )

    assert response.status_code == 400
    assert "Access-Control-Allow-Origin" not in response.headers


def test_error_responses_carry_cors_headers() -> None:
    response = _client().get("/nope", headers={"Origin": ALLOWED})

    assert response.status_code == 404
    assert response.headers["Access-Control-Allow-Origin"] == ALLOWED


@pytest.mark.parametrize(
    ("raw", "normalised"),
    [
        ("http://localhost:3000/", "http://localhost:3000"),
        ("HTTPS://App.Example.com", "https://app.example.com"),
        ("https://app.example.com:8443", "https://app.example.com:8443"),
    ],
)
def test_origin_is_normalised(raw: str, normalised: str) -> None:
    assert Settings(_env_file=None, web_origin=raw).web_origin == normalised


@pytest.mark.parametrize(
    "bad",
    [
        "*",
        "https://*.example.com",
        "app.example.com",
        "ftp://app.example.com",
        "https://app.example.com/dashboard",
        "https://app.example.com?x=1",
        "https://user:pw@app.example.com",
    ],
)
def test_invalid_origins_rejected(bad: str) -> None:
    with pytest.raises(ValidationError, match="single origin"):
        Settings(_env_file=None, web_origin=bad)


@pytest.mark.parametrize("origin", ["http://app.example.com", "https://localhost:3000"])
def test_deployed_environments_need_public_https_origin(origin: str) -> None:
    with pytest.raises(ValidationError, match="public https origin"):
        Settings(
            _env_file=None,
            app_env=Environment.PRODUCTION,
            app_db_password=SecretStr("a"),
            redis_password=SecretStr("b"),
            web_origin=origin,
        )
