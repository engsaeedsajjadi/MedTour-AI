import os
from sqlalchemy import select
from .database import Base, engine, SessionLocal
from .models import Tenant, User
from . import enterprise_models  # register tables
from .security import password_hash

def bootstrap():
    if os.getenv('APP_ENV','development')=='production':
        raise RuntimeError('Bootstrap from environment is development-only. Use a controlled production provisioning process.')
    password=os.environ['BOOTSTRAP_ADMIN_PASSWORD']
    email=os.environ.get('BOOTSTRAP_ADMIN_EMAIL','admin@example.invalid').strip().lower()
    slug=os.environ.get('TENANT_SLUG','medtour-local')
    name=os.environ.get('TENANT_NAME','MedTour Local')
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        tenant=db.scalar(select(Tenant).where(Tenant.slug==slug))
        if not tenant:
            tenant=Tenant(slug=slug,name=name)
            db.add(tenant); db.flush()
        exists=db.scalar(select(User).where(User.tenant_id==tenant.id,User.email==email))
        if exists: raise RuntimeError('Bootstrap user already exists; no overwrite performed')
        db.add(User(tenant_id=tenant.id,email=email,password_hash=password_hash(password),role='admin'))
        db.commit()
        print('Development bootstrap complete:',slug,email)

if __name__=='__main__': bootstrap()
