from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import ConflictError, NotFoundError


class _Payload(BaseModel):
    email: str
    age: int


def _add_test_routes(app: FastAPI) -> None:
    @app.get("/_test/not-found")
    async def not_found() -> None:
        raise NotFoundError("Lead not found.", code="LEAD_NOT_FOUND")

    @app.get("/_test/conflict")
    async def conflict() -> None:
        raise ConflictError(details=[{"field": "slug", "message": "Already taken."}])

    @app.post("/_test/validate")
    async def validate(payload: _Payload) -> _Payload:
        return payload

    @app.get("/_test/crash")
    async def crash() -> None:
        raise RuntimeError("database password is hunter2")


def _client(app: FastAPI) -> TestClient:
    _add_test_routes(app)
    return TestClient(app, raise_server_exceptions=False)


def _assert_envelope(body: dict[str, object], response_request_id: str) -> None:
    assert set(body) == {"error", "meta"}
    assert body["meta"] == {"request_id": response_request_id}


def test_app_error_uses_envelope(app: FastAPI) -> None:
    response = _client(app).get("/_test/not-found")

    assert response.status_code == 404
    body = response.json()
    _assert_envelope(body, response.headers["X-Request-ID"])
    assert body["error"] == {"code": "LEAD_NOT_FOUND", "message": "Lead not found.", "details": []}


def test_app_error_defaults_and_details(app: FastAPI) -> None:
    response = _client(app).get("/_test/conflict")

    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "CONFLICT",
        "message": "The request conflicts with the current state.",
        "details": [{"field": "slug", "message": "Already taken."}],
    }


def test_validation_error_lists_fields_without_echoing_input(app: FastAPI) -> None:
    secret_value = "s3cret-value-that-must-not-echo"
    response = _client(app).post(
        "/_test/validate", json={"email": secret_value, "age": "not-a-number"}
    )

    assert response.status_code == 422
    body = response.json()
    _assert_envelope(body, response.headers["X-Request-ID"])
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert [d["field"] for d in body["error"]["details"]] == ["body.age"]
    assert "not-a-number" not in response.text
    assert secret_value not in response.text


def test_unknown_route_returns_404_envelope(client: TestClient) -> None:
    response = client.get("/nope")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_wrong_method_returns_405_envelope(client: TestClient) -> None:
    response = client.post("/healthz")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
    assert "GET" in response.headers["Allow"]


def test_unhandled_exception_is_generic_500_without_internals(app: FastAPI) -> None:
    response = _client(app).get("/_test/crash")

    assert response.status_code == 500
    body = response.json()
    _assert_envelope(body, response.headers["X-Request-ID"])
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "hunter2" not in response.text
    assert "RuntimeError" not in response.text
