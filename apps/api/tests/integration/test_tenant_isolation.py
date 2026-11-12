"""Row Level Security behaves as ADR-006 requires.

A probe table is created with exactly the SQL that migrations will use
(``enable_tenant_rls_sql``) and exercised through the restricted app role.
"""

import uuid
from collections.abc import Iterator

import psycopg
import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.engine import (
    async_session_factory,
    create_async_db_engine,
    create_sync_db_engine,
    sync_session_factory,
)
from app.db.rls import enable_tenant_rls_sql
from app.db.tenant import set_tenant, set_tenant_sync
from tests.integration.conftest import owner_connect

TABLE = "rls_probe"
TENANT_A = uuid.UUID("0190a000-0000-7000-8000-00000000000a")
TENANT_B = uuid.UUID("0190b000-0000-7000-8000-00000000000b")


@pytest.fixture(scope="module")
def probe_table(integration_settings: Settings) -> Iterator[None]:
    with owner_connect(integration_settings) as conn:
        conn.execute(
            f"CREATE TABLE {TABLE} ("
            "id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
            "tenant_id uuid NOT NULL, label text NOT NULL)"
        )
        for statement in enable_tenant_rls_sql(TABLE):
            conn.execute(statement)
    yield
    with owner_connect(integration_settings) as conn:
        conn.execute(f"DROP TABLE {TABLE}")


@pytest.fixture
def engine(integration_settings: Settings, probe_table: None) -> Iterator[Engine]:
    # pool_size=1: every session reuses the same physical connection, which is
    # what proves that tenant context does not leak between transactions.
    settings = integration_settings.model_copy(update={"db_pool_size": 1, "db_max_overflow": 0})
    engine = create_sync_db_engine(settings)
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(TENANT_A)})
        conn.execute(text(f"DELETE FROM {TABLE}"))
        conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(TENANT_B)})
        conn.execute(text(f"DELETE FROM {TABLE}"))
    yield engine
    engine.dispose()


def _insert(engine: Engine, tenant: uuid.UUID, row_tenant: uuid.UUID, label: str) -> None:
    with sync_session_factory(engine).begin() as session:
        set_tenant_sync(session, tenant)
        session.execute(
            text(f"INSERT INTO {TABLE} (tenant_id, label) VALUES (:t, :l)"),
            {"t": row_tenant, "l": label},
        )


def _labels(engine: Engine, tenant: uuid.UUID | None) -> list[str]:
    with sync_session_factory(engine).begin() as session:
        if tenant is not None:
            set_tenant_sync(session, tenant)
        return list(session.execute(text(f"SELECT label FROM {TABLE} ORDER BY label")).scalars())


def _assert_rls_violation(exc: DBAPIError) -> None:
    assert isinstance(exc.orig, psycopg.errors.InsufficientPrivilege)
    assert "row-level security" in str(exc.orig)


def test_each_tenant_sees_only_its_rows(engine: Engine) -> None:
    _insert(engine, TENANT_A, TENANT_A, "a1")
    _insert(engine, TENANT_A, TENANT_A, "a2")
    _insert(engine, TENANT_B, TENANT_B, "b1")

    assert _labels(engine, TENANT_A) == ["a1", "a2"]
    assert _labels(engine, TENANT_B) == ["b1"]


def test_no_tenant_context_sees_nothing(engine: Engine) -> None:
    _insert(engine, TENANT_A, TENANT_A, "a1")

    assert _labels(engine, None) == []


def test_no_tenant_context_cannot_insert(engine: Engine) -> None:
    with pytest.raises(DBAPIError) as exc_info, sync_session_factory(engine).begin() as session:
        session.execute(
            text(f"INSERT INTO {TABLE} (tenant_id, label) VALUES (:t, 'x')"), {"t": TENANT_A}
        )

    _assert_rls_violation(exc_info.value)


def test_cannot_insert_row_for_another_tenant(engine: Engine) -> None:
    with pytest.raises(DBAPIError) as exc_info:
        _insert(engine, TENANT_A, TENANT_B, "smuggled")

    _assert_rls_violation(exc_info.value)
    assert _labels(engine, TENANT_B) == []


def test_cannot_move_own_row_to_another_tenant(engine: Engine) -> None:
    _insert(engine, TENANT_A, TENANT_A, "a1")

    with pytest.raises(DBAPIError) as exc_info, sync_session_factory(engine).begin() as session:
        set_tenant_sync(session, TENANT_A)
        session.execute(text(f"UPDATE {TABLE} SET tenant_id = :b"), {"b": TENANT_B})

    _assert_rls_violation(exc_info.value)


def test_cannot_update_or_delete_another_tenants_rows(engine: Engine) -> None:
    _insert(engine, TENANT_B, TENANT_B, "b1")

    with sync_session_factory(engine).begin() as session:
        set_tenant_sync(session, TENANT_A)
        updated = session.execute(text(f"UPDATE {TABLE} SET label = 'hacked'"))
        deleted = session.execute(text(f"DELETE FROM {TABLE}"))

    assert updated.rowcount == 0  # type: ignore[attr-defined]
    assert deleted.rowcount == 0  # type: ignore[attr-defined]
    assert _labels(engine, TENANT_B) == ["b1"]


def test_tenant_context_does_not_outlive_the_transaction(engine: Engine) -> None:
    _insert(engine, TENANT_A, TENANT_A, "a1")
    assert _labels(engine, TENANT_A) == ["a1"]

    # Same pooled connection (pool_size=1), new transaction, no set_tenant.
    assert _labels(engine, None) == []
    with engine.connect() as conn:
        setting = conn.execute(text("SELECT current_setting('app.tenant_id', true)")).scalar()
    assert setting in (None, "")


def test_set_tenant_rejects_non_uuid(engine: Engine) -> None:
    with pytest.raises(TypeError), sync_session_factory(engine).begin() as session:
        set_tenant_sync(session, "' OR 1=1 --")  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_async_session_isolation(integration_settings: Settings, probe_table: None) -> None:
    engine = create_async_db_engine(integration_settings)
    factory = async_session_factory(engine)
    try:
        for tenant, label in ((TENANT_A, "async-a"), (TENANT_B, "async-b")):
            async with factory.begin() as session:
                await set_tenant(session, tenant)
                await session.execute(
                    text(f"INSERT INTO {TABLE} (tenant_id, label) VALUES (:t, :l)"),
                    {"t": tenant, "l": label},
                )

        async def labels(session: AsyncSession) -> list[str]:
            result = await session.execute(
                text(f"SELECT label FROM {TABLE} WHERE label LIKE 'async-%'")
            )
            return list(result.scalars())

        async with factory.begin() as session:
            await set_tenant(session, TENANT_A)
            assert await labels(session) == ["async-a"]
        async with factory.begin() as session:
            assert await labels(session) == []
    finally:
        async with factory.begin() as session:
            for tenant in (TENANT_A, TENANT_B):
                await set_tenant(session, tenant)
                await session.execute(text(f"DELETE FROM {TABLE} WHERE label LIKE 'async-%'"))
        await engine.dispose()
