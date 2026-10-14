import os
from .database import Base, engine
from . import models, enterprise_models  # noqa

if __name__=='__main__':
    if os.getenv('APP_ENV','development')=='production':
        raise RuntimeError('Production needs reviewed schema migrations; create_all is development-only.')
    Base.metadata.create_all(bind=engine)
    print('Development schema created; NOT a production migration')
