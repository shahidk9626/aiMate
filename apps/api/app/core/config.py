"""Typed application settings loaded from environment variables.

Settings are read once at startup. Invalid or missing values fail fast with a
validation error instead of surfacing later as a runtime bug. Secrets use
``SecretStr`` so they are never printed in reprs or logs.

Sources, highest priority first: real environment variables, ``apps/api/.env``,
the repository-root ``.env`` (shared with docker compose). In containers only
real environment variables exist.
"""

import re
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

_API_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _API_DIR.parents[1]

# PostgreSQL role names are used as SQL identifiers in bootstrap/migrations.
_ROLE_NAME = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Later files override earlier ones; real env vars override both.
        env_file=(_REPO_ROOT / ".env", _API_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    app_name: str = "AI LeadFlow API"
    app_env: Environment = Environment.LOCAL
    log_level: LogLevel = "INFO"
    # JSON logs everywhere except an interactive local console.
    log_json: bool | None = Field(default=None)

    # --- PostgreSQL -----------------------------------------------------------
    postgres_host: str = "127.0.0.1"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = "leadflow"
    # Owner role: runs migrations and the role bootstrap. Not needed (and
    # should not be provided) where only the API/worker run.
    postgres_user: str = "leadflow_owner"
    postgres_password: SecretStr | None = None
    # Runtime role: no superuser, no BYPASSRLS, no DDL.
    app_db_user: str = "leadflow_app"
    app_db_password: SecretStr | None = None
    db_pool_size: int = Field(default=5, ge=1, le=100)
    db_max_overflow: int = Field(default=5, ge=0, le=100)
    db_connect_timeout_seconds: int = Field(default=5, ge=1, le=60)

    # --- Redis ----------------------------------------------------------------
    redis_host: str = "127.0.0.1"
    redis_port: int = Field(default=6379, ge=1, le=65535)
    redis_db: int = Field(default=0, ge=0, le=15)
    redis_password: SecretStr | None = None

    readiness_timeout_seconds: float = Field(default=2.0, gt=0, le=30)

    @field_validator("postgres_user", "app_db_user")
    @classmethod
    def _valid_role_name(cls, value: str) -> str:
        if not _ROLE_NAME.fullmatch(value):
            raise ValueError("must be a lowercase PostgreSQL identifier")
        return value

    @model_validator(mode="after")
    def _deployed_environments_need_secrets(self) -> Self:
        if self.app_env in (Environment.STAGING, Environment.PRODUCTION):
            missing = [
                name
                for name, value in (
                    ("APP_DB_PASSWORD", self.app_db_password),
                    ("REDIS_PASSWORD", self.redis_password),
                )
                if value is None or not value.get_secret_value()
            ]
            if missing:
                raise ValueError(f"required in {self.app_env.value}: {', '.join(missing)}")
        if self.app_db_user == self.postgres_user:
            raise ValueError("APP_DB_USER must differ from POSTGRES_USER (owner role)")
        return self

    # --- Derived values ---------------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.app_env is Environment.PRODUCTION

    @property
    def docs_enabled(self) -> bool:
        """Interactive API docs are not published in production."""
        return not self.is_production

    @property
    def use_json_logs(self) -> bool:
        if self.log_json is not None:
            return self.log_json
        return self.app_env is not Environment.LOCAL

    def _pg_url(self, user: str, password: SecretStr | None, database: str | None) -> URL:
        # URL.create escapes special characters in credentials safely.
        return URL.create(
            "postgresql+psycopg",
            username=user,
            password=password.get_secret_value() if password else None,
            host=self.postgres_host,
            port=self.postgres_port,
            database=database or self.postgres_db,
        )

    def database_url(self) -> URL:
        """Runtime connection as the restricted app role."""
        return self._pg_url(self.app_db_user, self.app_db_password, None)

    def migration_database_url(self, database: str | None = None) -> URL:
        """Owner connection for migrations and bootstrap only."""
        if self.postgres_password is None:
            raise RuntimeError("POSTGRES_PASSWORD is required for migrations and bootstrap")
        return self._pg_url(self.postgres_user, self.postgres_password, database)


@lru_cache
def get_settings() -> Settings:
    return Settings()
