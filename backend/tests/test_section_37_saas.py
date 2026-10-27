"""Section 37 local, synthetic subscription and tenant tests."""
def test_plan_catalog_and_tenant_isolation(context):
    client,auth,ids,Session=context
    a,b=auth("a"),auth("b")
    operator=auth("a","operator@example.test")
    url="/api/v1/saas/subscription"
    plans=client.get("/api/v1/saas/plans")
    assert plans.status_code==200
    assert plans.json()["purchase_available"] is False
    assert client.get(url).status_code==401
    assert client.get(url,headers=operator).status_code==403
    assert client.get(url,headers=a).json()["status"]=="not_configured"
    assert client.post(url+"/evaluation",headers=a,json={"plan_code":"unknown"}).status_code==422
    assert client.post(url+"/evaluation",headers=operator,json={"plan_code":"starter"}).status_code==403
    r=client.post(url+"/evaluation",headers=a,json={"plan_code":"starter"})
    assert r.status_code==200,r.text
    assert r.json()["charged"] is False
    assert r.json()["status"]=="evaluation"
    assert client.post(url+"/evaluation",headers=a,json={"plan_code":"enterprise"}).status_code==409
    assert client.get(url,headers=a).json()["plan"]=="starter"
    assert client.get(url,headers=b).json()["status"]=="not_configured"
    assert client.post(url+"/evaluation",headers=b,json={"plan_code":"professional"}).status_code==200
    assert client.get(url,headers=b).json()["plan"]=="professional"
    assert client.get(url,headers=a).json()["payment_verified"] is False
