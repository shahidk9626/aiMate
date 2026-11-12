import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import Environment, Settings
from app.core.logging import get_logger
from app.main import create_app


def _json_lines(output: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in output.splitlines() if line.startswith("{")]


def test_access_log_has_request_id_and_no_query_string(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    client = TestClient(create_app(settings))

    response = client.get("/api/v1/contacts?email=customer@example.com&phone=9999999999")

    records = [r for r in _json_lines(capsys.readouterr().out) if r.get("event") == "request"]
    assert len(records) == 1
    record = records[0]
    assert record["request_id"] == response.headers["X-Request-ID"]
    assert record["path"] == "/api/v1/contacts"
    assert record["method"] == "GET"
    assert record["status"] == 404
    assert "customer@example.com" not in json.dumps(record)
    assert "9999999999" not in json.dumps(record)


def test_sensitive_keys_are_redacted(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    create_app(settings)

    get_logger("test").info("login_attempt", password="hunter2", refresh_token="abc", user_id="u1")

    record = _json_lines(capsys.readouterr().out)[-1]
    assert record["password"] == "[REDACTED]"
    assert record["refresh_token"] == "[REDACTED]"
    assert record["user_id"] == "u1"


def test_unhandled_exception_logged_with_request_id(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    app = create_app(settings)

    @app.get("/_test/crash")
    async def crash() -> None:
        raise RuntimeError("boom")

    response = TestClient(app, raise_server_exceptions=False).get("/_test/crash")

    errors = [
        r for r in _json_lines(capsys.readouterr().out) if r.get("event") == "unhandled_exception"
    ]
    assert len(errors) == 1
    assert errors[0]["request_id"] == response.headers["X-Request-ID"]
    assert "RuntimeError: boom" in str(errors[0]["exception"])


def test_successful_health_probes_are_not_access_logged(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    client = TestClient(create_app(settings))

    client.get("/healthz")
    client.get("/healthz?x=1")

    records = [r for r in _json_lines(capsys.readouterr().out) if r.get("event") == "request"]
    assert records == []


def test_failed_health_probes_are_still_logged(capsys: pytest.CaptureFixture[str]) -> None:
    unreachable = Settings(
        _env_file=None,
        app_env=Environment.TEST,
        log_json=True,
        postgres_port=1,
        redis_port=1,
        readiness_timeout_seconds=1.0,
        db_connect_timeout_seconds=1,
    )
    with TestClient(create_app(unreachable)) as client:
        assert client.get("/readyz").status_code == 503

    records = [r for r in _json_lines(capsys.readouterr().out) if r.get("event") == "request"]
    assert [(r["path"], r["status"]) for r in records] == [("/readyz", 503)]


def test_startup_logs_trusted_web_origin(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    with TestClient(create_app(settings)):
        pass

    startup = [r for r in _json_lines(capsys.readouterr().out) if r.get("event") == "startup"]
    assert startup[0]["web_origin"] == settings.web_origin
