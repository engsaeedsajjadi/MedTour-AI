"""Live diagnostic, not a claim of production tenant isolation.

Authenticated admins can inspect how far PostgreSQL preparation has progressed.
If any privileged shared connection still exists, report NOT READY.
"""
from __future__ import annotations
from fastapi import APIRouter,Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from .database import get_db
from .models import User
from .security import roles

router=APIRouter(prefix="/api/v1/admin/tenant-isolation",tags=["tenant integrity"])
ADMIN=roles("admin")
SQL_TABLES="""
 SELECT COUNT(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 JOIN pg_attribute a ON a.attrelid=c.oid AND a.attname='tenant_id'
 WHERE n.nspname='public' AND c.relkind IN ('r','p')
   AND a.attnum>0 AND NOT a.attisdropped
"""
SQL_RLS=SQL_TABLES+" AND c.relrowsecurity AND c.relforcerowsecurity"

def audit_status(db:Session):
    if db.bind is None or db.bind.dialect.name!="postgresql":
        return {"database":"not_postgresql","tenant_scoped_tables":0,
            "composite_tenant_fks":0,"rls_policy_tables":0,"rls_force_tables":0,
            "runtime_role_nonprivileged":False,"authenticated_tenant_role":False,
            "verified_end_to_end_routing":False,"production_ready":False,
            "reason":"SQLite tests are not PostgreSQL RLS proof"}
    row=db.execute(text("""
        SELECT session_user::text, current_user::text,
               r.rolsuper, r.rolbypassrls, r.rolcreaterole
        FROM pg_roles r WHERE r.rolname=session_user
    """)).one()
    scoped=db.scalar(text(SQL_TABLES))
    forced=db.scalar(text(SQL_RLS))
    fks=db.scalar(text("""
       SELECT count(*) FROM pg_constraint con
       JOIN pg_class c ON c.oid=con.conrelid
       JOIN pg_namespace n ON n.oid=c.relnamespace
       WHERE n.nspname='public' AND con.contype='f'
       AND con.conname LIKE 'mt26_fk_%' AND con.convalidated
    """))
    policies=db.scalar(text("""
       SELECT count(*) FROM pg_policies
       WHERE schemaname='public' AND policyname='mt26_principal_isolation'
    """))
    safe_role=not any(row[2:])
    # Common API dependency still uses shared DATABASE_URL and has no
    # full authenticated pre-auth / patient portal / webhook routing.
    return {"database":"postgresql",
        "tenant_scoped_tables":scoped,
        "composite_tenant_fks":fks,
        "rls_policy_tables":policies,
        "rls_force_tables":forced,
        "runtime_role_nonprivileged":safe_role,
        "authenticated_tenant_role":False,
        "verified_end_to_end_routing":False,
        "production_ready":False,
        "reason":"Legacy shared get_db, pre-auth routes and runtime DB role migration outstanding"}

@router.get("/status")
def status(db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    # Never disclose actual password, role names, other tenant ids or DSNs.
    return audit_status(db)
