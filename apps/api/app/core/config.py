"""Typed application settings loaded from environment variables.

Settings are read once at startup. Invalid or missing values fail fast with a
validation error instead of surfacing later as a runtime bug. Secrets added in
later steps must use ``SecretStr`` so they are never printed in reprs or logs.
"""

from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Real environment variables always win over the file.
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    app_name: str = "AI LeadFlow API"
    app_env: Environment = Environment.LOCAL
    log_level: LogLevel = "INFO"
    # JSON logs everywhere except an interactive local console.
    log_json: bool | None = Field(default=None)

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
