"""Readiness without dependencies (unit). The live 200 case is in tests/integration."""

import time

from fastapi.testclient import TestClient

from app.core.config import Environment, Settings
from app.main import create_app


def _unreachable_settings() -> Settings:
    # Port 1 on localhost refuses connections immediately.
    return Settings(
        _env_file=None,
        app_env=Environment.TEST,
        postgres_port=1,
        redis_port=1,
        readiness_timeout_seconds=1.0,
        db_connect_timeout_seconds=1,
    )


def test_readyz_returns_503_when_dependencies_are_down() -> None:
    with TestClient(create_app(_unreachable_settings())) as client:
        started = time.perf_counter()
        response = client.get("/readyz")
        elapsed = time.perf_counter() - started

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "checks": {"database": "unavailable", "redis": "unavailable"},
    }
    # Checks run concurrently and are bounded by the timeout.
    assert elapsed < 2.5


def test_readyz_does_not_leak_connection_details() -> None:
    with TestClient(create_app(_unreachable_settings())) as client:
        body = client.get("/readyz").text

    for leak in ("127.0.0.1", "Connection refused", "psycopg", "leadflow_app"):
        assert leak not in body


def test_healthz_stays_ok_when_dependencies_are_down() -> None:
    with TestClient(create_app(_unreachable_settings())) as client:
        assert client.get("/healthz").status_code == 200
