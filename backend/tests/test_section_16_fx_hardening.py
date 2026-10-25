"""Section 16 financial hardening: manual FX is auditable, never a live feed."""
from datetime import datetime,timedelta,timezone
from app.enterprise_models import VerifiedFxRate,QuoteVersion
ROOT="/api/v1/quotation-versions"

def setup(client,admin,case_id):
    q=client.post("/api/v1/quotes",headers=admin,json={
        "case_id":case_id,"currency":"USD","amount_minor":0,"details":"Synthetic quote"})
    assert q.status_code==201,q.text
    p=client.post("/api/v1/prices",headers=admin,json={
        "service_code":"diagnostics","label":"Synthetic diagnostics","currency":"USD",
        "amount_minor":12345,"source":"SYNTHETIC-PROVIDER-REF",
        "valid_until":(datetime.now(timezone.utc)+timedelta(days=30)).isoformat()})
    assert p.status_code==201,p.text
    return q.json()["id"],p.json()["id"]

def make_rate(client,admin,num=1,den=2,from_ccy="EUR",to_ccy="USD",days=4):
    return client.post(ROOT+"/fx-rates",headers=admin,json={
        "source_currency":from_ccy,"target_currency":to_ccy,
        "numerator":num,"denominator":den,
        "source_reference":"SYNTHETIC-EXCHANGE-REF-16",
        "expires_at":(datetime.now(timezone.utc)+timedelta(days=days)).isoformat()
    })

def euro_price(client,admin):
    p=client.post("/api/v1/prices",headers=admin,json={
        "service_code":"transport","label":"Synthetic transport",
        "currency":"EUR","amount_minor":12345,
        "source":"SYNTHETIC-FOREIGN-QUOTE-16",
        "valid_until":(datetime.now(timezone.utc)+timedelta(days=15)).isoformat()
    })
    assert p.status_code==201,p.text
    return p.json()["id"]

def test_manual_fx_half_up_reconciliation_and_metadata(seeded):
    (client,auth,tids,Session),admin,p,case=seeded
    q,usd=setup(client,admin,case["id"])
    eur=euro_price(client,admin)
    rate=make_rate(client,admin)
    assert rate.status_code==201,rate.text
    fx_id=rate.json()["id"]
    assert rate.json()["live_fx_verified"] is False
    rates=client.get(ROOT+"/fx-rates",headers=admin)
    assert rates.status_code==200 and len(rates.json()["items"])==1
    assert client.get(ROOT+"/fx-rates",headers=auth("b")).json()["items"]==[]
    assert client.post(ROOT+"/fx-rates",headers=auth("a","operator@example.test"),json={
        "source_currency":"EUR","target_currency":"USD","numerator":1,"denominator":2,
        "source_reference":"SYNTHETIC-EXCHANGE-REF-16",
        "expires_at":(datetime.now(timezone.utc)+timedelta(days=4)).isoformat()
    }).status_code==403
    url=ROOT+f"/quotes/{q}/draft"
    no_fx=client.post(url,headers=admin,json={"lines":[{"price_id":eur,"units":1}]})
    assert no_fx.status_code==409
    wrong_fx=client.post(url,headers=admin,json={"lines":[{"price_id":usd,"units":1,"fx_rate_id":fx_id}]})
    assert wrong_fx.status_code==422
    good=client.post(url,headers=admin,json={"lines":[
        {"price_id":eur,"units":1,"fx_rate_id":fx_id},
        {"price_id":usd,"units":1}
    ]})
    assert good.status_code==201,good.text
    body=good.json()
    assert body["total_minor"]==6173+12345
    assert body["fx_conversion_used"] is True
    assert body["lines"][0]["source_total_minor"]==12345
    assert body["lines"][0]["fx_fraction"]=={"numerator":1,"denominator":2}
    assert body["lines"][0]["line_total_minor"]==6173
    approve=client.post(ROOT+"/versions/"+body["id"]+"/approve",headers=admin,
                        json={"reference":"ADMIN-QUOTE-REVIEW-16"})
    assert approve.status_code==200,approve.text
    pdf=client.get(ROOT+"/versions/"+body["id"]+"/pdf",headers=admin)
    assert pdf.status_code==200 and pdf.content.startswith(b"%PDF-")
    assert b"184" in pdf.content or len(pdf.content)>1000
    assert pdf.headers["content-type"].startswith("application/pdf")
    with Session() as db:assert db.query(VerifiedFxRate).count()==1

def test_revoked_fx_blocks_approval_and_legacy_edit_route(seeded):
    (client,auth,tids,Session),admin,p,case=seeded
    q,usd=setup(client,admin,case["id"])
    eur=euro_price(client,admin)
    fx=make_rate(client,admin).json()["id"]
    body=client.post(ROOT+f"/quotes/{q}/draft",headers=admin,json={
        "lines":[{"price_id":eur,"units":3,"fx_rate_id":fx}]})
    assert body.status_code==201,body.text
    assert client.post("/api/v1/quotes/"+q+"/items",headers=admin,json={
        "label":"Legacy backdoor line","units":1,"unit_amount_minor":300,
        "provenance":"LEGACY-QUOTE-REF"
    }).status_code==409
    assert client.post(ROOT+"/fx-rates/"+fx+"/revoke",headers=auth("b")).status_code==404
    assert client.post(ROOT+"/fx-rates/"+fx+"/revoke",headers=admin).status_code==200
    review=client.post(ROOT+"/versions/"+body.json()["id"]+"/approve",headers=admin,
                      json={"reference":"POST-FX-REVOKE-16"})
    assert review.status_code==409

def test_invalid_manual_fx_rate_and_wrong_pair_fail_closed(seeded):
    (client,auth,tids,Session),admin,p,case=seeded
    q,usd=setup(client,admin,case["id"])
    eur=euro_price(client,admin)
    assert make_rate(client,admin,from_ccy="USD",to_ccy="USD").status_code==422
    assert make_rate(client,admin,days=40).status_code==422
    assert make_rate(client,admin,num=0).status_code==422
    wrong=make_rate(client,admin,from_ccy="IRR",to_ccy="USD")
    assert wrong.status_code==201
    assert client.post(ROOT+f"/quotes/{q}/draft",headers=admin,json={
        "lines":[{"price_id":eur,"units":1,"fx_rate_id":wrong.json()["id"]}]
    }).status_code==409

def test_many_lines_generate_multi_page_pdf_without_oversized_single_page(seeded):
    (client,auth,tids,Session),admin,p,case=seeded
    q,price=setup(client,admin,case["id"])
    body=client.post(ROOT+f"/quotes/{q}/draft",headers=admin,json={
        "lines":[{"price_id":price,"units":1} for _ in range(40)]})
    assert body.status_code==201,body.text
    approved=client.post(ROOT+"/versions/"+body.json()["id"]+"/approve",headers=admin,json={
        "reference":"MULTIPAGE-QUOTE-16"})
    assert approved.status_code==200,approved.text
    pdf=client.get(ROOT+"/versions/"+body.json()["id"]+"/pdf",headers=admin)
    assert pdf.status_code==200,pdf.text[:100]
    # ReportLab page objects are generated for more than one A4 sheet.
    assert pdf.content.count(b"/Type /Page ")>=2
    assert len(pdf.content)<5_000_000
