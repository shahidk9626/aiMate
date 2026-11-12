import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from app.core.config import Environment, Settings
from app.main import create_app


def _settings(**overrides: object) -> Settings:
    # Staging/production require these secrets (see test_db_config.py).
    overrides.setdefault("app_db_password", SecretStr("test-only"))
    overrides.setdefault("redis_password", SecretStr("test-only"))
    overrides.setdefault("web_origin", "https://app.example.com")
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


def test_defaults_are_local_and_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("APP_ENV", "LOG_LEVEL", "LOG_JSON"):
        monkeypatch.delenv(var, raising=False)

    settings = _settings()

    assert settings.app_env is Environment.LOCAL
    assert settings.log_level == "INFO"
    assert settings.use_json_logs is False


def test_reads_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")

    settings = _settings()

    assert settings.app_env is Environment.PRODUCTION
    assert settings.log_level == "WARNING"
    assert settings.use_json_logs is True


@pytest.mark.parametrize(("var", "value"), [("APP_ENV", "prod"), ("LOG_LEVEL", "LOUD")])
def test_rejects_invalid_values(monkeypatch: pytest.MonkeyPatch, var: str, value: str) -> None:
    monkeypatch.setenv(var, value)

    with pytest.raises(ValidationError):
        _settings()


def test_settings_are_immutable() -> None:
    settings = _settings()

    with pytest.raises(ValidationError):
        settings.app_env = Environment.PRODUCTION  # type: ignore[misc]


def test_docs_published_outside_production() -> None:
    client = TestClient(create_app(_settings(app_env=Environment.STAGING)))

    assert client.get("/api/v1/openapi.json").status_code == 200
    assert client.get("/api/v1/docs").status_code == 200


def test_docs_hidden_in_production() -> None:
    client = TestClient(create_app(_settings(app_env=Environment.PRODUCTION)))

    assert client.get("/api/v1/openapi.json").status_code == 404
    assert client.get("/api/v1/docs").status_code == 404
