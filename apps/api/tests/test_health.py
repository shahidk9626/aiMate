from fastapi.testclient import TestClient


def test_healthz_returns_ok(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_is_not_under_versioned_api(client: TestClient) -> None:
    assert client.get("/api/v1/healthz").status_code == 404
