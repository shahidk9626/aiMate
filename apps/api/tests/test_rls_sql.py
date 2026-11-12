import pytest

from app.db.rls import disable_tenant_rls_sql, enable_tenant_rls_sql


def test_enable_forces_rls_and_checks_reads_and_writes() -> None:
    statements = enable_tenant_rls_sql("leads")

    assert statements[0] == "ALTER TABLE leads ENABLE ROW LEVEL SECURITY"
    assert statements[1] == "ALTER TABLE leads FORCE ROW LEVEL SECURITY"
    policy = statements[2]
    assert "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)" in policy
    assert "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)" in (
        policy
    )


def test_disable_reverses_enable() -> None:
    assert disable_tenant_rls_sql("leads") == [
        "DROP POLICY IF EXISTS tenant_isolation ON leads",
        "ALTER TABLE leads NO FORCE ROW LEVEL SECURITY",
        "ALTER TABLE leads DISABLE ROW LEVEL SECURITY",
    ]


@pytest.mark.parametrize("bad", ["Leads", "leads; DROP TABLE users", "1leads", "", "a" * 64])
def test_rejects_unsafe_table_names(bad: str) -> None:
    with pytest.raises(ValueError, match="invalid table name"):
        enable_tenant_rls_sql(bad)
    with pytest.raises(ValueError, match="invalid table name"):
        disable_tenant_rls_sql(bad)
