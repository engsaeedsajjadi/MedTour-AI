from __future__ import annotations
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./medtour_dev.sqlite3')
if DATABASE_URL.startswith('sqlite') and os.getenv('APP_ENV', 'development') == 'production':
    raise RuntimeError('SQLite is not allowed in production')
kwargs = {'connect_args': {'check_same_thread': False}} if DATABASE_URL.startswith('sqlite') else {'pool_pre_ping': True}
if DATABASE_URL == 'sqlite://':
    kwargs['poolclass'] = StaticPool
engine = create_engine(DATABASE_URL, **kwargs)
_shared_session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
def _strict_shared_session_blocked(*args,**kwargs):
    raise RuntimeError("Shared database sessions forbidden in tenant strict mode; use a verified tenant principal")

# Fail closed even if a background helper bypasses FastAPI dependencies and
# imports SessionLocal directly. Only the explicit tenant registry owns DB work.
SessionLocal = (_strict_shared_session_blocked
    if os.getenv("TENANT_DB_ROUTING_MODE","").lower()=="strict"
    else _shared_session_factory)

class Base(DeclarativeBase):
    pass

def get_db():
    if os.getenv("TENANT_DB_ROUTING_MODE","").lower()=="strict":
        raise RuntimeError("Tenant mode requires a verified request-bound database gateway")
    with SessionLocal() as db:
        yield db
