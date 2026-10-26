"""Section 26: disposable PostgreSQL 17 role isolation probe (NEVER live DB).

Run only in the synthetic GitHub Actions stack after Alembic upgrades.
It activates the staged policies in CI, constructs two nonprivileged DB
logins, tests cross-tenant reads and writes, and proves a forged GUC fails.
"""
from __future__ import annotations
import os,secrets
from uuid import uuid4
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.engine.url import make_url

def main():
    assert os.getenv("CI")=="true", "Section26 probe requires ephemeral CI"
    assert os.getenv("SECTION26_ISOLATED_PROBE")=="synthetic_only"
    url=make_url(os.environ["DATABASE_URL"])
    assert url.database=="medtour_ci" and url.host in ("127.0.0.1","localhost"), "Live database refused"
    tenants=[str(uuid4()),str(uuid4())]
    patients=[str(uuid4()),str(uuid4())]
    roles=["mt26_probe_a","mt26_probe_b"]
    passwords=[secrets.token_urlsafe(34),secrets.token_urlsafe(34)]
    owner=sa.create_engine(url,pool_pre_ping=True)
    with owner.begin() as conn:
        admin=conn.execute(text("""
            SELECT current_user,r.rolsuper,r.rolbypassrls
            FROM pg_roles r WHERE r.rolname=current_user
        """)).one()
        assert admin[1] is True, "CI setup must be database owner superuser"
        tables=conn.execute(text("""
            SELECT c.relname FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid
            JOIN pg_attribute a ON a.attrelid=c.oid
            WHERE n.nspname='public' AND c.relkind='r'
            AND a.attname='tenant_id' AND a.attnum>0 AND NOT a.attisdropped
            ORDER BY c.relname
        """)).scalars().all()
        assert len(tables)>=37, f"Expected whole enterprise schema, got {len(tables)}"
        fks=conn.execute(text("""
            SELECT COUNT(*) FROM pg_constraint WHERE conname LIKE 'mt26_fk_%'
        """)).scalar()
        assert fks>=48,f"Composite tenant FKs missing: {fks}"
        for table in tables:
            label='"'+table.replace('"','""')+'"'
            assert conn.execute(text(
                "SELECT EXISTS(SELECT 1 FROM pg_policies WHERE schemaname='public' "
                "AND tablename=:table AND policyname='mt26_principal_isolation')"
            ),{"table":table}).scalar(),table
            conn.execute(text(f"ALTER TABLE public.{label} ENABLE ROW LEVEL SECURITY"))
            conn.execute(text(f"ALTER TABLE public.{label} FORCE ROW LEVEL SECURITY"))
        for i in range(2):
            role=roles[i]
            conn.execute(text(f"CREATE ROLE {role} LOGIN PASSWORD '{passwords[i]}' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT"))
            conn.execute(text("INSERT INTO public.tenants(id,slug,name,created_at) VALUES"
                              " (:id,:slug,:name,now())"),{"id":tenants[i],"slug":f"probe26-{i}","name":"Synthetic DB Role"})
            conn.execute(text("INSERT INTO public.patients(id,tenant_id,full_name,country,language,contact,created_at) VALUES"
                              " (:id,:tenant,:name,'','en','',now())"),
                         {"id":patients[i],"tenant":tenants[i],"name":"synthetic patient"})
            conn.execute(text("INSERT INTO medtour_principal_private.role_tenant_mapping(database_role,tenant_id)"
                              " VALUES (:role,:tenant)"),{"role":role,"tenant":tenants[i]})
            conn.execute(text(f"GRANT USAGE ON SCHEMA public, medtour_principal_private TO {role}"))
            conn.execute(text(f"GRANT EXECUTE ON FUNCTION medtour_principal_private.tenant_for_login() TO {role}"))
            for table in tables:
                label='"'+table.replace('"','""')+'"'
                conn.execute(text(f"GRANT SELECT,INSERT,UPDATE,DELETE ON public.{label} TO {role}"))
        # Table owner is a superuser in disposable CI only; runtime roles are not.
    for i in range(2):
        scoped_url=url.set(username=roles[i],password=passwords[i])
        tenant_engine=sa.create_engine(scoped_url,pool_pre_ping=True,pool_size=1,max_overflow=0)
        try:
            with tenant_engine.connect() as conn:
                identity=conn.execute(text(
                    "SELECT session_user, current_user, medtour_principal_private.tenant_for_login()"
                )).one()
                assert identity==(roles[i],roles[i],tenants[i]),identity
                privileged=conn.execute(text("""
                    SELECT rolsuper,rolbypassrls,rolcreaterole
                    FROM pg_roles WHERE rolname=session_user
                """)).one()
                assert not any(privileged)
                for table in tables:
                    label='"'+table.replace('"','""')+'"'
                    n=conn.execute(text(f"SELECT COUNT(*) FROM public.{label} WHERE tenant_id<>:tenant"),
                                   {"tenant":tenants[i]}).scalar()
                    assert n==0,("Cross tenant rows readable",table,n)
                # RLS never relies on forgeable caller-controlled app GUC.
                conn.execute(text("SELECT set_config('medtour.tenant_id',:other,false)"),{"other":tenants[1-i]})
                mine=conn.execute(text("SELECT COUNT(*) FROM public.patients WHERE id=:id"),
                                  {"id":patients[i]}).scalar()
                foreign=conn.execute(text("SELECT COUNT(*) FROM public.patients WHERE id=:id"),
                                     {"id":patients[1-i]}).scalar()
                assert mine==1 and foreign==0
                conn.rollback()
                # Fail-closed updates: foreign records invisible.
                with conn.begin():
                    result=conn.execute(text(
                        "UPDATE public.patients SET full_name='forbidden' WHERE id=:other"),
                        {"other":patients[1-i]})
                    assert result.rowcount==0
                # Database enforces cross-tenant INSERT even without ORM filter.
                try:
                    with conn.begin():
                        conn.execute(text("""
                            INSERT INTO public.patients(id,tenant_id,full_name,country,language,contact,created_at)
                            VALUES (:id,:tenant,'attack','','en','',now())
                        """),{"id":str(uuid4()),"tenant":tenants[1-i]})
                    raise AssertionError("Cross-tenant insert unexpectedly accepted")
                except sa.exc.DBAPIError:
                    pass
                # A foreign-parent FK cannot be smuggled through a valid
                # tenant_id by bypassing the ORM. This exercises the newly
                # validated composite (tenant_id,patient_id) relationship.
                try:
                    with conn.begin():
                        conn.execute(text("""
                            INSERT INTO public.cases
                            (id,tenant_id,patient_id,complaint,specialty,status,created_at)
                            VALUES (:id,:tenant,:foreign,'','','new',now())
                        """),{"id":str(uuid4()),"tenant":tenants[i],
                               "foreign":patients[1-i]})
                    raise AssertionError("Cross-tenant case FK unexpectedly accepted")
                except sa.exc.DBAPIError:
                    pass
                # A valid same-tenant FK succeeds for restricted login role.
                with conn.begin():
                    conn.execute(text("""
                        INSERT INTO public.cases
                        (id,tenant_id,patient_id,complaint,specialty,status,created_at)
                        VALUES (:id,:tenant,:patient,'','','new',now())
                    """),{"id":str(uuid4()),"tenant":tenants[i],
                           "patient":patients[i]})
                                # All access to privileged registry is explicitly refused.
                try:
                    with conn.begin():
                        conn.execute(text("SELECT id FROM public.tenants LIMIT 1"))
                    raise AssertionError("Tenant bootstrap registry leaked")
                except sa.exc.DBAPIError:pass
                try:
                    with conn.begin():
                        conn.execute(text("SELECT * FROM medtour_principal_private.role_tenant_mapping"))
                    raise AssertionError("Private mapping leaked")
                except sa.exc.DBAPIError:pass
                try:
                    with conn.begin():
                        conn.execute(text(f"SET ROLE {roles[1-i]}"))
                    raise AssertionError("Cross-tenant role escalation permitted")
                except sa.exc.DBAPIError:pass
        finally:
            tenant_engine.dispose()
    with owner.connect() as conn:
        enabled=conn.execute(text("""
            SELECT count(*) FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid
            JOIN pg_attribute a ON a.attrelid=c.oid AND a.attname='tenant_id'
            WHERE n.nspname='public' AND c.relkind='r' AND c.relrowsecurity AND c.relforcerowsecurity
        """)).scalar()
        assert enabled==len(tables)
    owner.dispose()
    print(f"PASS: Section 26 PostgreSQL RLS {len(tables)} tables, {fks} composite tenant FKs, two authenticated DB principals, cross-tenant DML denied")

if __name__=="__main__":
    main()
