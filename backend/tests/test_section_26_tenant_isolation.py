"""Section26 diagnostics and non-production tenant isolation smoke tests."""
from app.tenant_isolation_status import audit_status
from app.models import Patient

STATUS="/api/v1/admin/tenant-isolation/status"

def test_diagnostic_reports_legacy_global_session_not_enterprise_ready(context):
    client,auth,_,Session=context
    admin=auth("a")
    op=auth("a","operator@example.test")
    assert client.get(STATUS).status_code==401
    assert client.get(STATUS,headers=op).status_code==403
    res=client.get(STATUS,headers=admin)
    assert res.status_code==200,res.text
    result=res.json()
    assert result["production_ready"] is False
    assert result["authenticated_tenant_role"] is False
    assert result["verified_end_to_end_routing"] is False
    assert result["composite_tenant_fks"]==0
    assert result["database"]=="not_postgresql"
    for forbidden in ("password","secret","dsn","postgres://","tenant_id"):
        assert forbidden not in res.text.lower()
    with Session() as db:
        assert audit_status(db)["production_ready"] is False


def test_legacy_tenant_scoped_api_guards_cross_tenant_updates(context):
    client,auth,_,Session=context
    a=auth("a");b=auth("b")
    made=client.post("/api/v1/patients",headers=a,json={
        "full_name":"Synthetic Tenant A","language":"fa","country":"AF"})
    assert made.status_code==201,made.text
    patient=made.json()["id"]
    assert client.get("/api/v1/patients/"+patient,headers=b).status_code==404
    # This ORM access guard complements but DOES NOT replace DB-level RLS.
    assert client.get("/api/v1/patients",headers=b).json()==[]
    with Session() as db:
        assert db.query(Patient).filter(Patient.id==patient).one().tenant_id is not None
