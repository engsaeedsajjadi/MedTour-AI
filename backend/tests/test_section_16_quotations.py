"""Section 16 synthetic finance safety regression."""
from datetime import datetime,timedelta,timezone
from app.enterprise_models import QuoteVersion
ROOT="/api/v1/quotation-versions"

def setup(client,admin,case_id):
    q=client.post("/api/v1/quotes",headers=admin,json={
        "case_id":case_id,"currency":"USD","amount_minor":0,"details":"Synthetic quote"});assert q.status_code==201,q.text
    p=client.post("/api/v1/prices",headers=admin,json={
        "service_code":"diagnostics","label":"Synthetic diagnostics","currency":"USD",
        "amount_minor":12345,"source":"SYNTHETIC-PROVIDER-REF",
        "valid_until":(datetime.now(timezone.utc)+timedelta(days=30)).isoformat()})
    assert p.status_code==201,p.text
    return q.json()["id"],p.json()["id"]

def test_revision_approval_pdf_and_immutability(seeded):
    (client,auth,tids,Session),admin,p,c=seeded
    q,price=setup(client,admin,c["id"])
    endpoint=ROOT+f"/quotes/{q}/draft"
    made=client.post(endpoint,headers=admin,json={"lines":[{"price_id":price,"units":2}]})
    assert made.status_code==201,made.text
    vid=made.json()["id"]
    assert made.json()["total_minor"]==24690
    assert made.json()["provider_cost_externally_verified"] is False
    assert client.get(ROOT+f"/versions/{vid}/pdf",headers=admin).status_code==409
    assert client.patch(f"/api/v1/quotes/{q}/approve",headers=admin).status_code==409
    assert client.post(ROOT+f"/versions/{vid}/approve",
        headers=auth("a","operator@example.test"),json={"reference":"QUOTE-REVIEW-0016"}).status_code==403
    a=client.post(ROOT+f"/versions/{vid}/approve",headers=admin,json={"reference":"QUOTE-REVIEW-0016"})
    assert a.status_code==200,a.text
    assert a.json()["status"]=="approved"
    assert client.post(endpoint,headers=admin,json={"lines":[{"price_id":price,"units":1}]}).status_code==409
    pdf=client.get(ROOT+f"/versions/{vid}/pdf",headers=admin)
    assert pdf.status_code==200 and pdf.content.startswith(b"%PDF-")
    assert b"24690" in pdf.content
    assert client.get(ROOT+f"/versions/{vid}/pdf",headers=auth("b")).status_code==404
    assert client.get(ROOT+f"/quotes/{q}",headers=auth("b")).status_code==404
    with Session() as db: assert db.query(QuoteVersion).count()==1

def test_draft_superseding_and_tenant_price_guards(seeded):
    (client,auth,tids,Session),admin,p,c=seeded
    q,price=setup(client,admin,c["id"])
    endpoint=ROOT+f"/quotes/{q}/draft"
    a=client.post(endpoint,headers=admin,json={"lines":[{"price_id":price,"units":1}]})
    assert a.status_code==201
    b=client.post(endpoint,headers=admin,json={"lines":[{"price_id":price,"units":3}]})
    assert b.status_code==201,b.text
    assert b.json()["version"]==2
    listing=client.get(ROOT+f"/quotes/{q}",headers=admin).json()["items"]
    assert listing[1]["status"]=="superseded"
    assert client.post(ROOT+f"/versions/{a.json()['id']}/approve",headers=admin,json={"reference":"OLD-QUOTE-0016"}).status_code==409
    assert client.post(endpoint,headers=auth("b"),json={"lines":[{"price_id":price,"units":2}]}).status_code==404
    assert client.post(endpoint,headers=admin,json={"lines":[{"price_id":"foreign-id","units":1}]}).status_code==404

def test_currency_mix_and_overflow_blocked(seeded):
    (client,auth,tids,Session),admin,p,c=seeded
    q,price=setup(client,admin,c["id"])
    eur=client.post("/api/v1/prices",headers=admin,json={
        "service_code":"transport","label":"Synthetic transport","currency":"EUR",
        "amount_minor":1200,"source":"SYNTHETIC-EUR-PROVIDER",
        "valid_until":(datetime.now(timezone.utc)+timedelta(days=12)).isoformat()})
    assert eur.status_code==201
    route=ROOT+f"/quotes/{q}/draft"
    assert client.post(route,headers=admin,json={"lines":[{"price_id":eur.json()["id"],"units":1}]}).status_code==409
    assert client.post(route,headers=admin,json={"lines":[{"price_id":price,"units":0}]}).status_code==422
    assert client.post(route,headers=admin,json={"lines":[{"price_id":price,"units":100001}]}).status_code==422

def test_consent_withdrawn_prevents_export_and_review(seeded):
    (client,auth,tids,Session),admin,p,c=seeded
    q,price=setup(client,admin,c["id"])
    a=client.post(ROOT+f"/quotes/{q}/draft",headers=admin,json={
        "lines":[{"price_id":price,"units":1}]})
    assert a.status_code==201
    revoke=client.post("/api/v1/consents",headers=admin,json={
        "patient_id":p["id"],"purpose":"intake","accepted":False,
        "notice_version":"quotation-16"})
    assert revoke.status_code==201
    assert client.post(ROOT+f"/versions/{a.json()['id']}/approve",
        headers=admin,json={"reference":"AFTER-REVOKE-16"}).status_code==409
    assert client.get(ROOT+f"/quotes/{q}",headers=admin).status_code==409
