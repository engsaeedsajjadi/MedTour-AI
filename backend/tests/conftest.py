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

@pytest.fixture()
def context():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session=sessionmaker(bind=engine,expire_on_commit=False)
    with Session() as s:
        ta=Tenant(slug='a',name='A');tb=Tenant(slug='b',name='B')
        s.add_all([ta,tb]);s.flush()
        ua=User(tenant_id=ta.id,email='a@example.test',password_hash=password_hash('test_password_12345'),role='admin')
        ub=User(tenant_id=tb.id,email='b@example.test',password_hash=password_hash('test_password_12345'),role='admin')
        op=User(tenant_id=ta.id,email='operator@example.test',password_hash=password_hash('test_password_12345'),role='operator')
        s.add_all([ua,ub,op]);s.commit()
        tids=(ta.id,tb.id)
    def get_test_db():
        with Session() as db: yield db
    app.dependency_overrides[get_db]=get_test_db
    client=TestClient(app)
    def auth(slug='a',email=None):
        r=client.post('/api/v1/auth/login',json={'tenant_slug':slug,'email':email or f'{slug}@example.test','password':'test_password_12345'})
        assert r.status_code==200,r.text
        return {'Authorization':'Bearer '+r.json()['access_token']}
    yield client,auth,tids,Session
    app.dependency_overrides.clear()
    engine.dispose()

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
