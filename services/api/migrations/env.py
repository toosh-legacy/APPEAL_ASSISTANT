from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from appeal_core.models import Base
from appeal_core.settings import get_settings
from sqlalchemy import create_engine

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_online() -> None:
    url = os.environ.get("ALEMBIC_DATABASE_URL") or get_settings().database_url
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
