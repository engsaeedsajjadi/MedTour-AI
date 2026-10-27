"""Section 38 policy tests: no tenant may enable privileged runtime capabilities."""
def test_tenant_config_policy_is_fail_closed(context):
    client,auth,ids,Session=context
    a,b=auth("a"),auth("b")
    operator=auth("a","operator@example.test")
    base="/api/v1/settings/"
    invalid=[
        ("feature_flags",{"enable_real_payments":True}),
        ("feature_flags",{"disable_rls":True}),
        ("feature_flags",{"show_help_tips":"true"}),
        ("feature_flags",["show_help_tips"]),
        ("locale","invalid"),
        ("enabled_languages",["fa","fa"]),
        ("enabled_languages",["fa","xx"]),
        ("public_portal",{"enable_patient_access":True}),
    ]
    for key,value in invalid:
        r=client.put(base+key,headers=a,json={"value":value})
        assert r.status_code==422,(key,r.status_code,r.text)
    assert client.put(base+"feature_flags",headers=operator,json={
        "value":{"show_help_tips":True}}).status_code==403
    ok=client.put(base+"feature_flags",headers=a,json={
        "value":{"show_help_tips":True,"compact_dashboard":False}})
    assert ok.status_code==200,ok.text
    assert client.get("/api/v1/settings",headers=a).json()["feature_flags"]["show_help_tips"] is True
    assert "feature_flags" not in client.get("/api/v1/settings",headers=b).json()
    assert client.put(base+"locale",headers=b,json={"value":"ar"}).status_code==200
    assert client.get("/api/v1/settings",headers=b).json()["locale"]=="ar"
    assert "locale" not in client.get("/api/v1/settings",headers=a).json()
