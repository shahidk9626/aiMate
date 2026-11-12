from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Environment, Settings
from app.core.errors import RateLimitedError
from app.main import create_app

ORIGIN = "http://localhost:3000"
CSRF = {"X-Requested-With": "leadflow"}


@pytest.fixture
def app() -> FastAPI:
    settings = Settings(
        _env_file=None, app_env=Environment.TEST, log_json=True, max_request_body_bytes=2048
    )
    app = create_app(settings)

    @app.post("/api/v1/_test/echo")
    async def echo(payload: dict[str, object]) -> dict[str, object]:
        return payload

    @app.post("/api/v1/webhooks/_test")
    async def webhook() -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/api/v1/_test/crash")
    async def crash() -> None:
        raise RuntimeError("boom")

    @app.get("/api/v1/_test/limited")
    async def limited() -> None:
        raise RateLimitedError(42)

    return app


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


# --- CSRF -----------------------------------------------------------------------------


def test_write_without_csrf_header_is_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/_test/echo", json={"a": 1}, headers={"Origin": ORIGIN})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_REJECTED"


def test_write_with_header_from_trusted_origin_is_allowed(client: TestClient) -> None:
    response = client.post("/api/v1/_test/echo", json={"a": 1}, headers={**CSRF, "Origin": ORIGIN})

    assert response.status_code == 200
    assert response.json() == {"a": 1}


def test_write_from_untrusted_origin_is_rejected_even_with_header(client: TestClient) -> None:
    for origin in ("https://evil.example", "null", "http://localhost:3001"):
        response = client.post(
            "/api/v1/_test/echo", json={"a": 1}, headers={**CSRF, "Origin": origin}
        )
        assert response.status_code == 403, origin


def test_non_browser_client_without_origin_needs_only_the_header(client: TestClient) -> None:
    assert client.post("/api/v1/_test/echo", json={}, headers=CSRF).status_code == 200
    assert client.post("/api/v1/_test/echo", json={}).status_code == 403


def test_reads_and_preflights_are_not_affected(client: TestClient) -> None:
    assert client.get("/healthz", headers={"Origin": "https://evil.example"}).status_code == 200
    preflight = client.options(
        "/api/v1/_test/echo",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type, x-requested-with",
        },
    )
    assert preflight.status_code == 200


def test_webhooks_are_exempt(client: TestClient) -> None:
    assert client.post("/api/v1/webhooks/_test").status_code == 200


def test_csrf_rejection_carries_cors_request_id_and_security_headers(client: TestClient) -> None:
    response = client.post("/api/v1/_test/echo", json={}, headers={"Origin": ORIGIN})

    assert response.headers["Access-Control-Allow-Origin"] == ORIGIN
    assert response.json()["meta"]["request_id"] == response.headers["X-Request-ID"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"


# --- body size limit ----------------------------------------------------------------


def test_declared_oversized_body_is_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/_test/echo", content=b"x" * 4096, headers=CSRF)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_streamed_oversized_body_without_length_is_rejected(client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(8):
            yield b'{"a":"' + b"x" * 500 + b'"}'

    response = client.post(
        "/api/v1/_test/echo",
        content=chunks(),
        headers={**CSRF, "Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_body_within_limit_is_accepted(client: TestClient) -> None:
    response = client.post("/api/v1/_test/echo", json={"a": "x" * 1000}, headers=CSRF)

    assert response.status_code == 200


# --- security headers ------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/healthz", "/api/v1/nope", "/api/v1/_test/crash"])
def test_security_headers_on_every_response(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_api_responses_are_not_cacheable(client: TestClient) -> None:
    assert client.get("/api/v1/nope").headers["Cache-Control"] == "no-store"


# --- errors ---------------------------------------------------------------------------


def test_unhandled_error_reaches_browser_with_cors_and_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/_test/crash", headers={"Origin": ORIGIN})

    assert response.status_code == 500
    assert response.headers["Access-Control-Allow-Origin"] == ORIGIN
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["meta"]["request_id"] == response.headers["X-Request-ID"]
    assert "boom" not in response.text


def test_rate_limited_error_returns_429_with_retry_after(client: TestClient) -> None:
    response = client.get("/api/v1/_test/limited")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "42"
    assert response.json()["error"]["code"] == "RATE_LIMITED"
