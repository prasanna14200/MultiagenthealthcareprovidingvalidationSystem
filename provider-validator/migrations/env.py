from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os, sys
sys.path.append(os.path.abspath('src'))
from src.db.models import Base
from dotenv import load_dotenv

load_dotenv()
config = context.config
fileConfig(config.config_file_name)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/providers.db")
target_metadata = Base.metadata

def run_migrations_offline():
    context.configure(
        url=DATABASE_URL, target_metadata=target_metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(
        {"sqlalchemy.url": DATABASE_URL},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
