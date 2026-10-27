"""Synthetic Section 29 financial reconciliation tests."""
def test_finance_reconciliation_multi_currency_isolation(context):
    client,auth,tids,Session=context
    a,b=auth("a"),auth("b")
    patient=client.post("/api/v1/patients",headers=a,json={"full_name":"Synthetic Patient"}).json()
    # Create intake consent required by case API.
    client.post("/api/v1/consents",headers=a,json={"patient_id":patient["id"],"purpose":"intake","accepted":True,"notice_version":"v1"})
    case=client.post("/api/v1/cases",headers=a,json={"patient_id":patient["id"],"specialty":"cardiology"})
    assert case.status_code==201,case.text
    cid=case.json()["id"]
    base="/api/v1/finance"
    assert client.get(base+"/reconciliation",headers=b,params={"case_id":cid}).status_code==404
    for kind,amount,currency,reference in [
        ("payment_received",20000,"USD","cash-payment-test-1"),
        ("refund_issued",5000,"USD","refund-test-1"),
        ("service_expense",3000,"USD","expense-test-1"),
        ("payment_received",9000,"EUR","payment-eur-test-1")]:
        response=client.post("/api/v1/enterprise/finance/entries",headers=a,json={
            "case_id":cid,"entry_type":kind,"currency":currency,
            "amount_minor":amount,"source_reference":reference})
        # Enterprise router prefix may vary; diagnostic assertion makes integration error explicit.
        assert response.status_code==201,response.text
    r=client.get(base+"/reconciliation",headers=a,params={"case_id":cid})
    assert r.status_code==200,r.text
    data=r.json()
    usd=next(x for x in data["currencies"] if x["currency"]=="USD")
    assert usd["received_minor"]==20000
    assert usd["refunded_minor"]==5000
    assert usd["net_after_expenses_minor"]==12000
    assert len(data["currencies"])==2
    assert data["cross_currency_total"] is None
    assert data["processor_settlement_verified"] is False
    assert client.get(base+"/reconciliation",headers=a,params={"case_id":cid,"limit":2}).status_code==409
    operator=auth("a","operator@example.test")
    assert client.get(base+"/reconciliation",headers=operator).status_code==403
    assert client.get(base+"/cases/"+cid+"/quote-comparison",headers=b).status_code==404
