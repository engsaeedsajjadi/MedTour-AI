"""Version-controlled schema migrations. Never run metadata.create_all in prod."""
from __future__ import annotations
import os
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config,pool
from app.database import Base
from app import models,enterprise_models,subscriptions # noqa: F401
config=context.config
if config.config_file_name:fileConfig(config.config_file_name)
target_metadata=Base.metadata
url=os.environ.get('DATABASE_URL')
if url:config.set_main_option('sqlalchemy.url',url.replace('%','%%'))

def offline():
    context.configure(url=config.get_main_option('sqlalchemy.url'),target_metadata=target_metadata,
       literal_binds=True,compare_type=True)
    with context.begin_transaction():context.run_migrations()

def online():
    engine=engine_from_config(config.get_section(config.config_ini_section),prefix='sqlalchemy.',
           poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection,target_metadata=target_metadata,compare_type=True)
        with context.begin_transaction():context.run_migrations()
    engine.dispose()
if context.is_offline_mode():offline()
else:online()
