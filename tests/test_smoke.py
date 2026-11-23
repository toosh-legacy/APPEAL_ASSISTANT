import pytest
from sqlalchemy import text


def test_settings_load():
    from appeal_core.settings import get_settings

    assert get_settings().llm_provider == "offline"


@pytest.mark.full
def test_db_has_vector_extension(db_session):
    assert db_session.execute(text("select extname from pg_extension where extname='vector'")).scalar() == "vector"
