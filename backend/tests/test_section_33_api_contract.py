"""Section 33 API contract regression tests: synthetic, no external provider."""
import re

def test_version_metadata_and_schema(context):
    client,_,_,_=context
    r=client.get("/api/v1/meta/contract")
    assert r.status_code==200
    body=r.json()
    assert body["api_major"]==1
    assert body["production_ready"] is False
    assert body["patient_data_authorized"] is False
    assert body["idempotency_coverage"]=="endpoint_specific_not_global"
    assert client.get(body["schema_url"]).status_code==200

def test_correlation_ids_are_generated_not_reflected(context):
    client,auth,_,_=context
    first=client.get("/api/v1/meta/contract",headers={"X-Request-ID":"patient-sensitive-injected"})
    second=client.get("/api/v1/meta/contract")
    one=first.headers["X-Request-ID"]
    two=second.headers["X-Request-ID"]
    assert re.fullmatch("[0-9a-f]{32}",one)
    assert one!=two
    assert one!="patient-sensitive-injected"
    assert first.headers["X-API-Major-Version"]=="1"
    unauth=client.get("/api/v1/patients")
    assert unauth.status_code==401
    assert re.fullmatch("[0-9a-f]{32}",unauth.headers["X-Request-ID"])
    assert "patient-sensitive-injected" not in unauth.text
