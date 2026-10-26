"""Section 22: multilingual public site, zero PHI, draft isolation and SEO gates.

All CMS text and settings in this suite are synthetic. The site does not
attest that hospitals, physicians, legal counsel, translations or live contact
information have been independently verified.
"""
from app.enterprise_models import ContentPage
from app.models import Audit

BASE="/api/v1"
SLUGS={"about","services","process","faq","contact",
       "privacy","terms","medical-disclaimer"}
LOCALES={"fa","ar","en","ps","prs"}

def manifest(client,tenant="a"):
    return client.get(BASE+"/public/"+tenant+"/site-manifest")

def bootstrap(client,admin):
    return client.post(BASE+"/cms/public-site/bootstrap",headers=admin,json={})

def _cms_specialists(client,admin):
    cached=getattr(client,"_section22_cms_specialists",None)
    if cached:return cached
    result={}
    pwd="SyntheticSection23ReviewerPassword"
    for stage,role in (("translation","cms_translator"),
                       ("medical","cms_medical_reviewer"),
                       ("legal","cms_legal_reviewer")):
        email="section22-"+stage+"@example.com"
        created=client.post(BASE+"/cms/workflow/reviewers",headers=admin,
            json={"email":email,"password":pwd,"role":role})
        assert created.status_code==201,created.text
        login=client.post(BASE+"/auth/login",json={"tenant_slug":"a",
            "email":email,"password":pwd})
        assert login.status_code==200,login.text
        result[stage]={"Authorization":"Bearer "+login.json()["access_token"]}
    setattr(client,"_section22_cms_specialists",result)
    return result

def publish(client,admin,record):
    reviewers=_cms_specialists(client,admin)
    page_id=record["id"]
    submitted=client.post(BASE+"/cms/workflow/pages/"+page_id+"/submit",headers=admin)
    assert submitted.status_code==200,submitted.text
    for stage,headers in reviewers.items():
        decision=client.post(BASE+"/cms/workflow/pages/"+page_id+"/reviews/"+stage,
            headers=headers,json={"decision":"approved",
                "evidence_reference":"SYNTH-SEC22-"+stage})
        assert decision.status_code==200,decision.text
    return client.patch(BASE+"/cms/pages/"+page_id+"/publish",headers=admin)

def setting(client,admin,payload):
    return client.put(BASE+"/settings/public_portal",headers=admin,
                      json={"value":payload})


def test_no_unreviewed_content_leaks_and_tenant_not_found(context):
    client,auth,ids,Session=context
    empty=manifest(client)
    assert empty.status_code==200,empty.text
    j=empty.json()
    assert j["pages"]==[]
    assert j["all_languages_complete"] is False
    assert j["search_indexing_allowed"] is False
    assert set(j["missing_translations"])==LOCALES
    assert all(set(x)==SLUGS for x in j["missing_translations"].values())
    assert manifest(client,"unknown-tenant").status_code==404
    assert manifest(client,"b").json()["pages"]==[]
    admin=auth("a")
    seeded=bootstrap(client,admin)
    assert seeded.status_code==201,seeded.text
    assert seeded.json()["created"]==40
    assert seeded.json()["published"]==0
    assert seeded.json()["manual_legal_medical_translation_review_required"] is True
    assert manifest(client).json()["pages"]==[]
    for lang in LOCALES:
        for slug in SLUGS:
            assert client.get(f"{BASE}/public/a/pages/{lang}/{slug}").status_code==404
    assert manifest(client,"b").json()["pages"]==[]
    assert client.get(BASE+"/cms/pages").status_code==401
    assert client.get(BASE+"/cms/public-site/drafts/"+seeded.json()["items"][0]["id"]).status_code==401
    with Session() as db:
        rows=db.query(ContentPage).all()
        assert len(rows)==40 and all(p.status=="draft" for p in rows)
        assert db.query(Audit).filter(Audit.event=="public_website_template_drafted").count()==40


def test_bootstrap_idempotent_preserves_edits(context):
    client,auth,ids,Session=context
    admin=auth("a")
    entries=bootstrap(client,admin).json()["items"]
    one=next(x for x in entries if x["slug"]=="about" and x["locale"]=="en")
    detail=client.get(BASE+"/cms/public-site/drafts/"+one["id"],headers=admin)
    assert detail.status_code==200
    assert detail.json()["status"]=="draft"
    assert len(detail.json()["body"])>60
    edited=client.post(BASE+"/cms/workflow/pages/"+one["id"]+"/versions",headers=admin,json={
        "title":"Synthetic approved informational about",
        "body":"Synthetic, legally and medically unverified informational text.",
        "expected_version":1,"reason":"Approved draft rewrite before staged specialist review"})
    assert edited.status_code==201,edited.text
    assert bootstrap(client,admin).json()["created"]==0
    assert client.get(BASE+"/cms/workflow/pages/"+one["id"]+"/versions",headers=admin).json()["items"][0]["title"]=="Synthetic approved informational about"
    assert client.get(BASE+"/cms/public-site/drafts/"+one["id"],headers=auth("b")).status_code==404
    operator=auth("a","operator@example.test")
    assert bootstrap(client,operator).status_code==403
    assert client.patch(BASE+"/cms/public-site/drafts/"+one["id"],headers=operator,json={
        "title":"Unauthorized edit","body":"Content"}).status_code==403
    assert client.post(BASE+"/cms/workflow/pages/"+one["id"]+"/versions",headers=admin,json={
        "title":"Should reject","body":"Text","expected_version":2,
        "reason":"Synthetic invalid edit","patient_id":"SENSITIVE"}).status_code==422
    pub=publish(client,admin,one)
    assert pub.status_code==200
    assert client.patch(BASE+"/cms/public-site/drafts/"+one["id"],headers=admin,json={
        "title":"Cannot silently change live text","body":"Changed"}).status_code==409
    data=client.get(BASE+"/public/a/pages/en/about")
    assert data.status_code==200
    assert data.json()["title"]=="Synthetic approved informational about"
    assert data.json()["body"].startswith("Synthetic, legally")


def test_published_only_manifest_language_fallback_and_crawl_gates(context):
    client,auth,ids,Session=context
    admin=auth("a")
    entries=bootstrap(client,admin).json()["items"]
    en_about=next(x for x in entries if x["slug"]=="about" and x["locale"]=="en")
    publish(client,admin,en_about)
    m=manifest(client).json()
    assert m["pages"]==[{"slug":"about","translations":{
        "en":{**m["pages"][0]["translations"]["en"]}}}]
    assert m["pages"][0]["translations"]["en"]["title"]
    assert "about" not in m["missing_translations"]["en"]
    assert "about" in m["missing_translations"]["ar"]
    assert client.get(BASE+"/public/a/pages/fa/about").status_code==404
    assert client.get(BASE+"/public/a/pages/en/about").status_code==200
    assert setting(client,admin,{"search_indexing_enabled":True,
        "legal_content_reviewed":True}).status_code==200
    assert manifest(client).json()["search_indexing_allowed"] is False
    for entry in entries:
        if entry["id"]==en_about["id"]:continue
        x=publish(client,admin,entry)
        assert x.status_code==200,x.text
    m=manifest(client).json()
    assert len(m["pages"])==8
    assert m["all_languages_complete"] is True
    assert all(not missing for missing in m["missing_translations"].values())
    assert m["search_indexing_allowed"] is True
    assert m["independent_legal_approval_verified"] is False
    assert m["clinical_provider_verified"] is False
    assert m["accepts_real_patient_information"] is False
    for pg in m["pages"]:
        assert set(pg["translations"])==LOCALES
        assert set(pg["translations"][x]["locale"] for x in LOCALES)==LOCALES
        assert "patient_id" not in str(pg)
    assert manifest(client,"b").json()["pages"]==[]


def test_unpublish_is_immediate_and_disables_indexing(context):
    client,auth,ids,Session=context
    admin=auth("a")
    entries=bootstrap(client,admin).json()["items"]
    for x in entries:assert publish(client,admin,x).status_code==200
    setting(client,admin,{"search_indexing_enabled":True,"legal_content_reviewed":True})
    assert manifest(client).json()["search_indexing_allowed"] is True
    legal=next(x for x in entries if x["slug"]=="privacy" and x["locale"]=="ar")
    operator=auth("a","operator@example.test")
    assert client.patch(BASE+"/cms/public-site/pages/"+legal["id"]+"/unpublish",headers=operator).status_code==403
    removed=client.patch(BASE+"/cms/public-site/pages/"+legal["id"]+"/unpublish",headers=admin)
    assert removed.status_code==200,removed.text
    assert removed.json()["status"]=="draft"
    assert client.get(BASE+"/public/a/pages/ar/privacy").status_code==404
    assert client.get(BASE+"/public/a/pages/fa/privacy").status_code==200
    assert manifest(client).json()["search_indexing_allowed"] is False
    assert manifest(client).json()["missing_translations"]["ar"]==["privacy"]
    assert client.patch(BASE+"/cms/public-site/pages/"+legal["id"]+"/unpublish",headers=admin).status_code==409
    assert client.patch(BASE+"/cms/public-site/pages/"+legal["id"]+"/unpublish",headers=auth("b")).status_code==404
    with Session() as db:
        assert db.query(Audit).filter(Audit.event=="public_website_page_unpublished").count()==1


def test_public_portal_setting_must_be_explicit_self_attestation(context):
    client,auth,_,_=context
    admin=auth("a")
    for item in bootstrap(client,admin).json()["items"]:publish(client,admin,item)
    assert manifest(client).json()["all_languages_complete"] is True
    for configuration in [
        {},
        {"search_indexing_enabled":True},
        {"legal_content_reviewed":True},
        {"search_indexing_enabled":"true","legal_content_reviewed":True},
        {"search_indexing_enabled":True,"legal_content_reviewed":"true"},
    ]:
        assert setting(client,admin,configuration).status_code==200
        assert manifest(client).json()["search_indexing_allowed"] is False
    assert setting(client,admin,{"search_indexing_enabled":True,
        "legal_content_reviewed":True}).status_code==200
    assert manifest(client).json()["search_indexing_allowed"] is True
    assert client.get(BASE+"/public/not-there/site-manifest").status_code==404


def test_pashto_and_dari_are_distinct_and_private_until_published(context):
    client,auth,_,Session=context
    admin=auth("a")
    entries=bootstrap(client,admin).json()["items"]
    ps=next(x for x in entries if x["slug"]=="services" and x["locale"]=="ps")
    prs=next(x for x in entries if x["slug"]=="services" and x["locale"]=="prs")
    assert client.get(BASE+"/public/a/pages/ps/services").status_code==404
    assert client.get(BASE+"/public/a/pages/prs/services").status_code==404
    assert publish(client,admin,ps).status_code==200
    assert publish(client,admin,prs).status_code==200
    pashto=client.get(BASE+"/public/a/pages/ps/services").json()
    dari=client.get(BASE+"/public/a/pages/prs/services").json()
    assert pashto["locale"]=="ps" and dari["locale"]=="prs"
    assert pashto["body"]!=dari["body"]
    assert manifest(client).json()["search_indexing_allowed"] is False


def test_safe_plaintext_content_not_script_executed_by_api(context):
    client,auth,_,_=context
    admin=auth("a")
    result=client.post(BASE+"/cms/pages",headers=admin,json={
        "slug":"faq","locale":"fa","title":"سؤالات ساختگی",
        "body":'<script>alert("xss")</script> متن نمایشی بدون ذخیره‌ی HTML اجرایی'})
    assert result.status_code==201
    assert client.get(BASE+"/public/a/pages/fa/faq").status_code==404
    assert publish(client,admin,result.json()).status_code==200
    out=client.get(BASE+"/public/a/pages/fa/faq")
    assert out.status_code==200
    assert out.headers.get("content-type","").startswith("application/json")
    # Text remains inert source data. Server renders it via normal React escaping.
    assert out.json()["body"].startswith("<script>")
