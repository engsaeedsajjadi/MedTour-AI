import os
os.environ['APP_ENV']='test'
os.environ['DATABASE_URL']='sqlite://'
os.environ['JWT_SECRET']='test_secret_very_long_at_least_thirty_two_bytes'
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.database import Base,get_db
from app.models import Tenant,User
from app.security import password_hash

# Optional PostgreSQL mode: MEDTOUR_TEST_PG=postgresql+psycopg://owner@host:port/db
# The API then runs as the non-privileged RLS role exactly like production,
# while tests inspect rows through the owner connection.
PG_URL=os.environ.get('MEDTOUR_TEST_PG','')
_pg_state={}
def _pg_engines():
    if _pg_state: return _pg_state['admin'],_pg_state['app']
    from sqlalchemy import text
    from sqlalchemy.engine import make_url
    from app import enterprise_models  # noqa: F401  register all tables
    from app.tenant_rls import install_rls,set_app_role_login
    admin=create_engine(PG_URL)
    with admin.begin() as c:
        c.execute(text('DROP SCHEMA IF EXISTS public CASCADE'));c.execute(text('CREATE SCHEMA public'))
    Base.metadata.create_all(admin)
    with admin.begin() as c:
        install_rls(c);set_app_role_login(c,'app_role_test_password_123')
    app_url=make_url(PG_URL).set(username='medtour_app',password='app_role_test_password_123')
    app_engine=create_engine(app_url)
    _pg_state.update(admin=admin,app=app_engine)
    return admin,app_engine
def _pg_reset(admin):
    from sqlalchemy import text
    names=', '.join('"'+t.name+'"' for t in Base.metadata.sorted_tables)
    with admin.begin() as c: c.execute(text(f'TRUNCATE {names} RESTART IDENTITY CASCADE'))

@pytest.fixture()
def context():
    from app.rate_limit import _hits
    _hits.clear()
    if PG_URL:
        admin_engine,app_engine=_pg_engines();_pg_reset(admin_engine);engine=None
        Session=sessionmaker(bind=admin_engine,expire_on_commit=False)
        AppSession=sessionmaker(bind=app_engine,expire_on_commit=False)
    else:
        engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(engine)
        Session=sessionmaker(bind=engine,expire_on_commit=False)
        AppSession=Session
    with Session() as s:
        ta=Tenant(slug='a',name='A');tb=Tenant(slug='b',name='B')
        s.add_all([ta,tb]);s.flush()
        ua=User(tenant_id=ta.id,email='a@example.test',password_hash=password_hash('test_password_12345'),role='admin')
        ub=User(tenant_id=tb.id,email='b@example.test',password_hash=password_hash('test_password_12345'),role='admin')
        op=User(tenant_id=ta.id,email='operator@example.test',password_hash=password_hash('test_password_12345'),role='operator')
        s.add_all([ua,ub,op]);s.commit()
        tids=(ta.id,tb.id)
    def get_test_db():
        with AppSession() as db: yield db
    app.dependency_overrides[get_db]=get_test_db
    client=TestClient(app)
    def auth(slug='a',email=None):
        r=client.post('/api/v1/auth/login',json={'tenant_slug':slug,'email':email or f'{slug}@example.test','password':'test_password_12345'})
        assert r.status_code==200,r.text
        return {'Authorization':'Bearer '+r.json()['access_token']}
    yield client,auth,tids,Session
    app.dependency_overrides.clear()
    if engine is not None: engine.dispose()

@pytest.fixture()
def seeded(context):
    client,auth,ids,Session=context
    a=auth('a')
    p=client.post('/api/v1/patients',headers=a,json={'full_name':'Synthetic Patient','language':'en','country':'AF'}).json()
    c=client.post('/api/v1/consents',headers=a,json={'patient_id':p['id'],'purpose':'intake','accepted':True,'notice_version':'v1'})
    assert c.status_code==201,c.text
    case=client.post('/api/v1/cases',headers=a,json={'patient_id':p['id'],'complaint':'request for review','specialty':'cardiology'})
    assert case.status_code==201,case.text
    return context,a,p,case.json()

@pytest.fixture()
def pg_engines():
    """(owner_engine, app_role_engine) of the PostgreSQL test database; skips on SQLite."""
    if not PG_URL: pytest.skip('requires MEDTOUR_TEST_PG')
    return _pg_engines()
