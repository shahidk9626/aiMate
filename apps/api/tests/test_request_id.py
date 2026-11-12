import re

import pytest
from fastapi.testclient import TestClient

HEX32 = re.compile(r"^[0-9a-f]{32}$")


def test_generates_request_id_when_absent(client: TestClient) -> None:
    response = client.get("/healthz")

    assert HEX32.fullmatch(response.headers["X-Request-ID"])


def test_each_request_gets_a_distinct_id(client: TestClient) -> None:
    first = client.get("/healthz").headers["X-Request-ID"]
    second = client.get("/healthz").headers["X-Request-ID"]

    assert first != second


def test_propagates_safe_incoming_request_id(client: TestClient) -> None:
    response = client.get("/healthz", headers={"X-Request-ID": "edge-abc123.XYZ_9"})

    assert response.headers["X-Request-ID"] == "edge-abc123.XYZ_9"


@pytest.mark.parametrize(
    "unsafe",
    [
        "short",  # under 8 characters
        "x" * 65,  # over 64 characters
        "abc def ghi",  # whitespace
        "<script>alert(1)</script>",
        "id\twith\ttabs",
    ],
)
def test_replaces_unsafe_incoming_request_id(client: TestClient, unsafe: str) -> None:
    response = client.get("/healthz", headers={"X-Request-ID": unsafe})

    assert HEX32.fullmatch(response.headers["X-Request-ID"])


def test_request_id_present_on_error_responses(client: TestClient) -> None:
    response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.json()["meta"]["request_id"] == response.headers["X-Request-ID"]
