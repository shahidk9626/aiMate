import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Environment, Settings


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


def test_runtime_url_uses_app_role_and_psycopg() -> None:
    settings = _settings(
        postgres_host="db",
        postgres_port=6543,
        postgres_db="crm",
        app_db_user="runtime",
        app_db_password=SecretStr("pw"),
    )

    url = settings.database_url()

    assert url.drivername == "postgresql+psycopg"
    assert (url.username, url.password, url.host, url.port, url.database) == (
        "runtime",
        "pw",
        "db",
        6543,
        "crm",
    )


def test_special_characters_in_password_are_escaped() -> None:
    settings = _settings(app_db_password=SecretStr("p@ss:/w#rd?"))

    rendered = settings.database_url().render_as_string(hide_password=False)

    assert "p%40ss%3A%2Fw%23rd%3F" in rendered


def test_urls_hide_password_when_printed() -> None:
    settings = _settings(app_db_password=SecretStr("topsecret"))

    assert "topsecret" not in str(settings.database_url())
    assert "topsecret" not in repr(settings)


def test_migration_url_uses_owner_role_and_optional_database() -> None:
    settings = _settings(postgres_user="owner", postgres_password=SecretStr("pw"))

    assert settings.migration_database_url().username == "owner"
    assert settings.migration_database_url("postgres").database == "postgres"


def test_migration_url_requires_owner_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="POSTGRES_PASSWORD"):
        _settings().migration_database_url()


@pytest.mark.parametrize("env", [Environment.STAGING, Environment.PRODUCTION])
def test_deployed_environments_require_secrets(
    monkeypatch: pytest.MonkeyPatch, env: Environment
) -> None:
    for var in ("APP_DB_PASSWORD", "REDIS_PASSWORD"):
        monkeypatch.delenv(var, raising=False)

    with pytest.raises(ValidationError, match="APP_DB_PASSWORD, REDIS_PASSWORD"):
        _settings(app_env=env)

    ok = _settings(
        app_env=env,
        app_db_password=SecretStr("a"),
        redis_password=SecretStr("b"),
        web_origin="https://app.example.com",
    )
    assert ok.app_env is env


def test_app_role_must_differ_from_owner() -> None:
    with pytest.raises(ValidationError, match="must differ"):
        _settings(postgres_user="same_role", app_db_user="same_role")


@pytest.mark.parametrize("bad", ["App", "app-role", "app;drop", "1app", ""])
def test_role_names_must_be_safe_identifiers(bad: str) -> None:
    with pytest.raises(ValidationError, match="PostgreSQL identifier"):
        _settings(app_db_user=bad)
