"""Section 32 audit pure evaluation and guardrails."""
import pytest
from app.db_schema_audit import assess,inspect

def test_empty_catalog_fails_closed():
    r=assess([],[])
    assert r["schema_review_passed"] is False
    assert "no_tenant_tables" in r["findings"]
    assert r["production_authorized"] is False

def test_inactive_rls_detected():
    tables=[dict(table_name="cases",has_principal_policy=True,tenant_id_unique=True,
                 rls_enabled=False,rls_forced=False)]
    r=assess(tables,[dict(child_table="cases",fk_column="patient_id",
                         has_tenant_fk=False)])
    assert "rls_not_enabled:cases" in r["findings"]
    assert "rls_not_forced:cases" in r["findings"]
    assert "missing_composite_tenant_fk:cases:patient_id" in r["findings"]

def test_complete_catalog_checks_never_mean_runtime_certification():
    r=assess([dict(table_name="patients",has_principal_policy=True,
       tenant_id_unique=True,rls_enabled=True,rls_forced=True)],[])
    assert r["schema_review_passed"] is True
    assert r["production_authorized"] is False
    assert r["runtime_tenant_routing_verified"] is False

def test_non_postgres_audit_rejected():
    class Dummy:
        class dialect:
            name="sqlite"
    with pytest.raises(RuntimeError,match="PostgreSQL"):
        inspect(Dummy())
