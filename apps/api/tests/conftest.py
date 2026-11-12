from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Environment, Settings
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    # Explicit values: tests must not depend on the developer's .env.
    return Settings(app_env=Environment.TEST, log_level="INFO", log_json=True, _env_file=None)


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    # raise_server_exceptions=False so 500 responses can be asserted like a real client sees them.
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
