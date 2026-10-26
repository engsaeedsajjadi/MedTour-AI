"""Synthetic section 23 CMS governance: no independent professional certification."""
from app.enterprise_models import ContentPage,CmsVersion,CmsReview,CmsWorkflowEvent

W="/api/v1/cms/workflow"
P="/api/v1"

def staff(client,admin):
    credentials={}
    for stage,role in [
        ("translation","cms_translator"),
        ("medical","cms_medical_reviewer"),
        ("legal","cms_legal_reviewer"),
        ("editor","cms_editor"),
    ]:
        email="section23-"+stage+"@example.com"
        account=client.post(W+"/reviewers",headers=admin,json={
            "email":email,"role":role,"password":"ReviewerSyntheticSection23Pass"})
        assert account.status_code==201,account.text
        assert account.json()["credentials_independently_verified"] is False
        login=client.post(P+"/auth/login",json={"tenant_slug":"a",
            "email":email,"password":"ReviewerSyntheticSection23Pass"})
        assert login.status_code==200,login.text
        credentials[stage]={"Authorization":"Bearer "+login.json()["access_token"]}
    return credentials

def page(client,admin,slug="public-test"):
    result=client.post(P+"/cms/pages",headers=admin,json={
        "slug":slug,"locale":"en",
        "title":"Synthetic public information","body":"Nonclinical synthetic source text"})
    assert result.status_code==201,result.text
    return result.json()["id"]

def submit(client,admin,page_id):
    result=client.post(W+"/pages/"+page_id+"/submit",headers=admin)
    assert result.status_code==200,result.text
    return result.json()

def review(client,page_id,reviewers,stage,decision="approved"):
    result=client.post(W+"/pages/"+page_id+"/reviews/"+stage,
        headers=reviewers[stage],json={"decision":decision,
            "evidence_reference":"SYNTH-REFERENCE-"+stage})
    assert result.status_code==200,result.text
    return result.json()

def approvals(client,page_id,reviewers):
    for stage in ("translation","medical","legal"):
        review(client,page_id,reviewers,stage)

def publish(client,admin,id):
    return client.patch(P+"/cms/pages/"+id+"/publish",headers=admin)


def test_three_independent_specialists_required_and_legacy_bypass_blocked(context):
    client,auth,_,Session=context
    admin=auth("a")
    id=page(client,admin)
    external=P+"/public/a/pages/en/public-test"
    assert client.get(external).status_code==404
    assert publish(client,admin,id).status_code==409
    users=staff(client,admin)
    assert client.get(W+"/pages",headers=users["medical"]).status_code==200
    assert client.get(P+"/patients",headers=users["medical"]).status_code==403
    assert client.get(P+"/cms/pages",headers=users["legal"]).status_code==403
    assert client.post(W+"/pages/"+id+"/submit",headers=users["legal"]).status_code==403
    submit(client,admin,id)
    assert publish(client,admin,id).status_code==409
    wrong=client.post(W+"/pages/"+id+"/reviews/medical",
        headers=users["translation"],json={"decision":"approved",
          "evidence_reference":"SYNTH-WRONG-ROLE"})
    assert wrong.status_code==403
    review(client,id,users,"translation")
    assert publish(client,admin,id).status_code==409
    review(client,id,users,"medical")
    assert publish(client,admin,id).status_code==409
    assert client.post(W+"/pages/"+id+"/reviews/medical",
        headers=users["medical"],json={"decision":"approved",
          "evidence_reference":"SYNTH-DUPLICATE"}).status_code==409
    result=review(client,id,users,"legal")
    assert result["version_state"]=="ready"
    assert publish(client,users["legal"],id).status_code==403
    final=publish(client,admin,id)
    assert final.status_code==200,final.text
    assert final.json()["version_no"]==1 and final.json()["human_review_count"]==3
    assert final.json()["legal_or_medical_credentials_independently_verified"] is False
    assert client.get(external).json()["title"]=="Synthetic public information"
    assert publish(client,admin,id).status_code==409
    with Session() as db:
        approvals_db=db.query(CmsReview).all()
        assert len(approvals_db)==3
        assert len({x.reviewer_id for x in approvals_db})==3
        version=db.query(CmsVersion).one()
        assert version.status=="published"
        assert len(version.content_hash)==64
        assert len(db.query(CmsWorkflowEvent).all())>=6


def test_new_version_keeps_previous_public_page_until_new_approvals(context):
    client,auth,_,Session=context
    admin=auth("a")
    users=staff(client,admin)
    id=page(client,admin)
    submit(client,admin,id);approvals(client,id,users);assert publish(client,admin,id).status_code==200
    published=P+"/public/a/pages/en/public-test"
    original=client.get(published).json()
    new=client.post(W+"/pages/"+id+"/versions",headers=users["editor"],json={
        "expected_version":1,"title":"New public headline",
        "body":"Edited safe and nonclinical information for review.",
        "reason":"Updated informational disclosure"})
    assert new.status_code==201,new.text
    assert new.json()["version_no"]==2
    assert client.get(published).json()==original
    assert publish(client,admin,id).status_code==409
    assert client.post(W+"/pages/"+id+"/versions",headers=users["editor"],json={
        "expected_version":1,"title":"Stale change","body":"Nonclinical change",
        "reason":"Bad stale version attempt"}).status_code==409
    assert client.post(W+"/pages/"+id+"/submit",headers=users["medical"]).status_code==403
    assert client.post(W+"/pages/"+id+"/submit",headers=users["editor"]).status_code==200
    assert client.post(W+"/pages/"+id+"/reviews/medical",headers=admin,json={
        "decision":"approved","evidence_reference":"SYNTH-ADMIN-OVERRIDE"}).status_code==403
    approvals(client,id,users)
    assert client.get(published).json()==original
    assert publish(client,admin,id).status_code==200
    assert client.get(published).json()["title"]=="New public headline"
    with Session() as db:
        all_versions=db.query(CmsVersion).order_by(CmsVersion.version_no).all()
        assert [v.version_no for v in all_versions]==[1,2]
        assert all_versions[0].title=="Synthetic public information"
        assert all_versions[1].author_id!=all_versions[0].author_id


def test_rejection_restore_requires_fresh_staged_approvals(context):
    client,auth,_,Session=context
    admin=auth("a")
    users=staff(client,admin)
    id=page(client,admin)
    original=client.get(W+"/pages/"+id+"/versions",headers=admin).json()["items"][0]
    modified=client.post(W+"/pages/"+id+"/versions",headers=admin,json={
        "title":"Rejected content","body":"Synthetic rejected page text",
        "expected_version":1,"reason":"Proposed alternative content"})
    assert modified.status_code==201
    submit(client,admin,id)
    review(client,id,users,"translation")
    decision=review(client,id,users,"medical","rejected")
    assert decision["version_state"]=="rejected"
    assert publish(client,admin,id).status_code==409
    assert client.post(W+"/pages/"+id+"/reviews/legal",headers=users["legal"],json={
        "decision":"approved","evidence_reference":"SYNTH-LATE-REVIEW"}).status_code==409
    restored=client.post(W+"/pages/"+id+"/versions/"+original["id"]+"/restore",
        headers=users["editor"],json={"expected_version":2,
        "reason":"Restore previously authored informational content"})
    assert restored.status_code==201,restored.text
    assert restored.json()["version_no"]==3
    assert restored.json()["restored_from"]==1
    assert restored.json()["reviews_reset"] is True
    assert publish(client,admin,id).status_code==409
    assert client.get(P+"/public/a/pages/en/public-test").status_code==404
    submit(client,users["editor"],id)
    approvals(client,id,users)
    assert publish(client,admin,id).status_code==200
    assert client.get(P+"/public/a/pages/en/public-test").json()["title"]==original["title"]
    versions=client.get(W+"/pages/"+id+"/versions",headers=admin).json()["items"]
    assert [v["version_no"] for v in versions]==[3,2,1]
    assert versions[1]["status"]=="rejected"


def test_editor_permission_and_isolation_across_tenants(context):
    client,auth,_,Session=context
    admin=auth("a")
    id=page(client,admin)
    users=staff(client,admin)
    outsider=auth("b")
    for url in [W+"/pages/"+id+"/versions",W+"/pages/"+id+"/history"]:
        assert client.get(url,headers=outsider).status_code==404
    assert client.get(W+"/pages",headers=outsider).json()["items"]==[]
    assert client.post(W+"/pages/"+id+"/versions",headers=outsider,json={
        "expected_version":1,"title":"Cross-tenant content",
        "body":"Synthetic forbidden text","reason":"Unauthorized action"}).status_code==404
    assert client.get(W+"/pages",headers=users["medical"]).status_code==200
    assert client.post(W+"/pages/"+id+"/versions",headers=users["medical"],json={
        "expected_version":1,"title":"Cannot edit","body":"Cannot edit",
        "reason":"Role must be editor"}).status_code==403
    assert client.post(W+"/reviewers",headers=users["editor"],json={
        "email":"another@example.com","role":"cms_legal_reviewer",
        "password":"SyntheticAnotherLongPass"}).status_code==403
    assert client.get(W+"/pages/"+id+"/versions").status_code==401


def test_unpublish_is_immutable_and_requires_new_approvals(context):
    client,auth,_,Session=context
    admin=auth("a")
    users=staff(client,admin)
    id=page(client,admin)
    submit(client,admin,id);approvals(client,id,users)
    assert publish(client,admin,id).status_code==200
    assert client.patch(P+"/cms/public-site/pages/"+id+"/unpublish",headers=admin).status_code==200
    assert client.get(P+"/public/a/pages/en/public-test").status_code==404
    assert publish(client,admin,id).status_code==409
    current=client.get(W+"/pages/"+id+"/versions",headers=admin).json()["items"][0]
    assert current["status"]=="withdrawn"
    changed=client.post(W+"/pages/"+id+"/versions",headers=users["editor"],json={
        "expected_version":1,"title":"Safe refreshed public content",
        "body":"A new and independently reviewed public content snapshot.",
        "reason":"New review after emergency unpublish"})
    assert changed.status_code==201,changed.text
    submit(client,users["editor"],id);approvals(client,id,users)
    assert publish(client,admin,id).status_code==200
    assert client.get(P+"/public/a/pages/en/public-test").json()["title"]=="Safe refreshed public content"
