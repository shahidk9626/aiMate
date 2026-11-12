"""The running app against real PostgreSQL and Redis."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import Settings
from app.db.session import DbSession
from app.db.tenant import set_tenant
from app.main import create_app


def test_readyz_ok_with_live_dependencies(integration_settings: Settings) -> None:
    with TestClient(create_app(integration_settings)) as client:
        response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok", "redis": "ok"}}


def test_db_session_dependency_runs_in_one_transaction_as_app_role(
    integration_settings: Settings,
) -> None:
    app = create_app(integration_settings)
    tenant = uuid.uuid4()

    @app.get("/_test/db")
    async def db_probe(session: DbSession) -> dict[str, str | None]:
        await set_tenant(session, tenant)
        row = (
            await session.execute(
                text("SELECT current_user, current_setting('app.tenant_id', true)")
            )
        ).one()
        return {"user": row[0], "tenant": row[1]}

    with TestClient(app) as client:
        body = client.get("/_test/db").json()

    assert body == {"user": integration_settings.app_db_user, "tenant": str(tenant)}
