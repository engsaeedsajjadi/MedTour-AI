"""Run only on a synthetic/restored PostgreSQL clone with a catalog reader DSN.

Does not print database connection URLs, usernames, or patient records.
"""
from __future__ import annotations
import json,os,sys
from sqlalchemy import create_engine
from app.db_schema_audit import inspect

def main():
    dsn=os.getenv("SCHEMA_AUDIT_DATABASE_URL","")
    if not dsn.startswith(("postgresql://","postgresql+psycopg://","postgresql+psycopg2://")):
        print("SCHEMA_AUDIT_DATABASE_URL must be a PostgreSQL catalog-reader DSN",file=sys.stderr)
        return 2
    if os.getenv("MEDTOUR_SYNTHETIC_CLONE")!="1":
        print("Audit restricted to synthetic/restored clone (MEDTOUR_SYNTHETIC_CLONE=1)",file=sys.stderr)
        return 2
    engine=create_engine(dsn,pool_pre_ping=True)
    try:
        with engine.connect() as db:
            result=inspect(db)
    finally:
        engine.dispose()
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result["schema_review_passed"] else 1

if __name__=="__main__":
    sys.exit(main())
