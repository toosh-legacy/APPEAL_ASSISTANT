"""Shared fixtures. Full-mode tests need the Docker services; they are skipped (never deleted) when absent."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _pg_available(url: str) -> bool:
    try:
        import psycopg

        with psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://"), connect_timeout=3):
            return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def test_db_url() -> str:
    from appeal_core.settings import get_settings

    s = get_settings()
    admin = s.database_url
    if not _pg_available(admin):
        pytest.skip("Postgres not available (lite environment); full-mode test skipped")
    import psycopg

    dbname = s.test_database_url.rsplit("/", 1)[1]
    with psycopg.connect(admin.replace("postgresql+psycopg://", "postgresql://"), autocommit=True) as conn:
        exists = conn.execute("select 1 from pg_database where datname=%s", (dbname,)).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{dbname}"')
    env = {**os.environ, "ALEMBIC_DATABASE_URL": s.test_database_url}
    subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env)
    return s.test_database_url


@pytest.fixture()
def db_session(test_db_url):
    from appeal_core.db import session_factory

    s = session_factory(test_db_url)()
    yield s
    s.rollback()
    s.close()
