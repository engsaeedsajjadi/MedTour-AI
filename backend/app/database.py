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
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

def get_db():
    with SessionLocal() as db:
        yield db
