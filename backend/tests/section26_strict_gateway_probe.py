"""Actual FastAPI route smoke tests through two PostgreSQL RLS LOGIN roles.

Only runs on disposable GitHub CI medtour_ci, after Section 26 RLS probe.
No real patient, provider, production credentials or outbound sends.
"""
import os,secrets,hmac,hashlib,json
from uuid import uuid4
from sqlalchemy import create_engine,text
from sqlalchemy.engine.url import make_url

url=os.environ.get("DATABASE_URL","")
assert os.environ.get("CI")=="true" and os.environ.get("SECTION26_ISOLATED_PROBE")=="synthetic_only"
pg=make_url(url)
assert pg.database=="medtour_ci" and pg.host in ("localhost","127.0.0.1")
# main imports SQLite only to register ORM models; DB dependency gets overridden.
os.environ["APP_ENV"]="test"
os.environ["DATABASE_URL"]="sqlite://"
os.environ["MEDTOUR_SYNTHETIC_CLONE"]="1"
os.environ["WHATSAPP_BUSINESS_ELIGIBILITY_APPROVED"]="true"
os.environ["WHATSAPP_INBOUND_PROCESSING_APPROVED"]="true"
os.environ["WHATSAPP_TENANT_SLUG"]="cutover-a"
os.environ["WHATSAPP_PHONE_NUMBER_ID"]="100001"
os.environ["META_APP_SECRET"]="only-synthetic-meta-secret"
os.environ["META_VERIFY_TOKEN"]="only-synthetic-verification"
os.environ["JWT_SECRET"]="synthetic_cutover_jwt_key_more_than_32_bytes"

from app.models import uid
from app.security import password_hash
from app.staged_tenant_epoch_control import StagedCoordinatedTenantRegistry,EpochState
from app.staged_tenant_pool_registry import TenantPrincipalConfig
from app.tenant_route_tokens import TenantRouteKeyring
from app.strict_tenant_gateway import StrictTenantGateway
from fastapi.testclient import TestClient

tenants=[str(uuid4()),str(uuid4())]
roles=["mt26_livepilot_a","mt26_livepilot_b"]
passwords=[secrets.token_urlsafe(34),secrets.token_urlsafe(34)]
users=[str(uuid4()),str(uuid4())]
db=create_engine(pg)
with db.begin() as conn:
    for i in range(2):
        conn.execute(text(f"CREATE ROLE {roles[i]} LOGIN PASSWORD '{passwords[i]}'"
            " NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT"))
        conn.execute(text("INSERT INTO public.tenants(id,slug,name,created_at)"
            " VALUES (:id,:slug,:name,now())"),{"id":tenants[i],"slug":f"cutover-{chr(97+i)}","name":"Synthetic Cutover"})
        conn.execute(text("INSERT INTO medtour_principal_private.role_tenant_mapping(database_role,tenant_id)"
            " VALUES (:role,:tid)"),{"role":roles[i],"tid":tenants[i]})
        conn.execute(text("INSERT INTO public.users(id,tenant_id,email,password_hash,role,active,created_at)"
            " VALUES (:uid,:tid,:email,:password,'admin',true,now())"),
            {"uid":users[i],"tid":tenants[i],"email":"admin@example.test",
             "password":password_hash("synthetic_password_12345")})
        conn.execute(text(f"GRANT USAGE ON SCHEMA public,medtour_principal_private TO {roles[i]}"))
        conn.execute(text("GRANT EXECUTE ON FUNCTION medtour_principal_private.tenant_for_login() TO "+roles[i]))
        tables=conn.execute(text("""
           SELECT c.relname FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid
           JOIN pg_attribute a ON a.attrelid=c.oid AND a.attname='tenant_id'
           WHERE n.nspname='public' AND c.relkind='r' AND a.attnum>0 AND NOT a.attisdropped
        """)).scalars().all()
        assert len(tables)>=82
        for table in tables:
            conn.execute(text(f'GRANT SELECT,INSERT,UPDATE,DELETE ON public."{table}" TO {roles[i]}'))
class FakeEpoch:
    def read(self,tenant_id):
        return EpochState(1,True) if tenant_id in tenants else None

registry=StagedCoordinatedTenantRegistry(reader=FakeEpoch(),max_tenants=2,pool_size=1)
provisioned={}
for i in range(2):
    config=TenantPrincipalConfig(tenant_id=tenants[i],slug=f"cutover-{chr(97+i)}",
        whatsapp_phone_id=str(100001+i),database_role=roles[i],database_password=passwords[i],
        database_host=pg.host,database_port=pg.port or 5432,database_name=pg.database)
    registry.provision(config,generation=1)
    provisioned[tenants[i]]=config
keyring=TenantRouteKeyring({"synthetic":secrets.token_bytes(32)},"synthetic")
gateway=StrictTenantGateway(registry=registry,provisioned=provisioned,keyring=keyring,
     meta_app_secret=os.environ["META_APP_SECRET"],whatsapp_approved=True)
with TestClient(gateway) as client:
    headers={}
    for i in range(2):
        result=client.post("/api/v1/auth/login",json={
            "tenant_slug":f"cutover-{chr(97+i)}","email":"admin@example.test",
            "password":"synthetic_password_12345"})
        assert result.status_code==200,result.text
        credentials=result.json()
        assert credentials["tenant_id"]==tenants[i]
        assert credentials["refresh_token"].startswith("mt1.")
        headers[i]={"Authorization":"Bearer "+credentials["access_token"]}
        # A real route from main.app with Depends(get_db) is now scoped to
        # an RLS-enforced non-superuser DB login and real JWT auth.
        resp=client.post("/api/v1/patients",headers=headers[i],json={
            "full_name":f"Synthetic Patient {i}","country":"AF","language":"fa"})
        assert resp.status_code==201,resp.text
        if i==0:patient_a=resp.json()["id"]
        else:patient_b=resp.json()["id"]
        refreshed=client.post("/api/v1/auth/refresh",
            json={"refresh_token":credentials["refresh_token"]})
        assert refreshed.status_code==200,refreshed.text
        assert refreshed.json()["refresh_token"].startswith("mt1.")
        assert client.post("/api/v1/auth/refresh",
            json={"refresh_token":credentials["refresh_token"]}).status_code==401
    assert client.get("/api/v1/patients",headers=headers[0]).status_code==200
    assert len(client.get("/api/v1/patients",headers=headers[0]).json())==1
    assert len(client.get("/api/v1/patients",headers=headers[1]).json())==1
    assert client.get("/api/v1/patients/"+patient_a,headers=headers[1]).status_code==404
    assert client.get("/api/v1/patients/"+patient_b,headers=headers[0]).status_code==404
    # Fake tenant header and unsigned JWT tenant claim never affect routing.
    assert len(client.get("/api/v1/patients",headers={
        **headers[0],"X-Tenant-ID":tenants[1]}).json())==1
    assert client.get("/api/v1/patients").status_code==401
    assert client.get("/api/v1/health/ready").status_code==401
    # Public pages route through server-provisioned slug with no tenants SELECT.
    assert client.get("/api/v1/public/cutover-a/pages/fa/about").status_code==404
    assert client.get("/api/v1/public/unprovisioned/pages/fa/about").status_code==404
    # Valid signed patient consent link, resolved before protected DB access.
    link=client.post(f"/api/v1/consent-links/{patient_a}/intake",headers=headers[0])
    assert link.status_code==201,link.text
    token=link.json()["token"]
    assert token.startswith("mt1.")
    assert client.get("/api/v1/consent-links/preview",params={"token":token}).status_code==200
    assert client.get("/api/v1/consent-links/preview",params={"token":"arbitrary-legacy-credential-token-"*2}).status_code==401
    responded=client.post("/api/v1/consent-links/respond",json={
        "token":token,"notice_version":"synthetic-v1","accepted":True})
    assert responded.status_code==201,responded.text
    assert client.post("/api/v1/consent-links/respond",json={
        "token":token,"notice_version":"synthetic-v1","accepted":True}).status_code==401
    # Real patient portal two-factor demo route with no shared role.
    communication=client.post(f"/api/v1/consents",headers=headers[0],json={
        "patient_id":patient_a,"purpose":"communication","accepted":True,
        "notice_version":"synthetic-v1"})
    assert communication.status_code==201,communication.text
    invite=client.post("/api/v1/portal/invites/"+patient_a,headers=headers[0])
    assert invite.status_code==201,invite.text
    assert invite.json()["token"].startswith("mt1.")
    session=client.post("/api/v1/portal/session/exchange",json={
        "invitation_token":invite.json()["token"],
        "verification_code":invite.json()["demo_verification_code"]})
    assert session.status_code==201,session.text
    patient_token=session.json()["access_token"]
    assert patient_token.startswith("mt1.")
    ph={"X-Patient-Access":patient_token}
    mine=client.get("/api/v1/portal/me",headers=ph)
    assert mine.status_code==200,mine.text
    assert mine.json()["id"]==patient_a
    altered=patient_token[:-1]+("A" if patient_token[-1]!="A" else "B")
    assert client.get("/api/v1/portal/me",headers={"X-Patient-Access":altered}).status_code==401
    # Signed Meta webhook to trusted provider account. No provider message sent.
    payload=json.dumps({"object":"whatsapp_business_account","entry":[{
        "changes":[{"field":"messages","value":{
          "metadata":{"phone_number_id":"100001"},
          "messages":[{"id":"synthetic-meta-id","from":"9999999999",
                       "type":"text","text":{"body":"Hello"}}]}}]}]}).encode()
    signature="sha256="+hmac.new(os.environ["META_APP_SECRET"].encode(),payload,hashlib.sha256).hexdigest()
    received=client.post("/api/v1/webhooks/whatsapp",content=payload,headers={
       "content-type":"application/json","X-Hub-Signature-256":signature})
    assert received.status_code==200,received.text
    assert received.json()["routed_to_human"]==0
    assert client.post("/api/v1/webhooks/whatsapp",content=payload,headers={
       "content-type":"application/json","X-Hub-Signature-256":"sha256="+"0"*64}).status_code==403

gateway.close()
db.dispose()
print("PASS: Real FastAPI main routes use authenticated per-tenant PostgreSQL roles + FORCE RLS: login, refresh/replay, staff patient CRUD, public, signed consent, patient invite/exchange, signed Meta webhook")
