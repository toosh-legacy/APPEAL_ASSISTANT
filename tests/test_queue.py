import pytest
from appeal_core.adapters.queue_postgres import PostgresJobQueue
from appeal_core.db import get_engine, session_factory
from sqlalchemy import text

pytestmark = pytest.mark.full


@pytest.fixture()
def q(test_db_url):
    with get_engine(test_db_url).begin() as c:
        c.execute(text("DELETE FROM job"))
    return PostgresJobQueue(url=test_db_url)


def _enqueue(q, url, n=1, topic="t"):
    s = session_factory(url)()
    ids = [q.enqueue(s, topic, {"i": i}) for i in range(n)]
    s.commit()
    s.close()
    return ids


def test_outbox_rolled_back_with_transaction(q, test_db_url):
    s = session_factory(test_db_url)()
    q.enqueue(s, "t", {})
    s.rollback()
    s.close()
    assert q.claim("w") is None


def test_skip_locked_two_workers_get_different_jobs(q, test_db_url):
    _enqueue(q, test_db_url, 2)
    a, b = q.claim("w1"), q.claim("w2")
    assert a and b and a.id != b.id
    assert q.claim("w3") is None


def test_retry_then_dead_letter(q, test_db_url):
    _enqueue(q, test_db_url, 1)
    for i in range(5):
        with get_engine(test_db_url).begin() as c:
            c.execute(text("UPDATE job SET available_at = now() - interval '1 second'"))
        job = q.claim("w")
        assert job is not None and job.attempts == i + 1
        outcome = q.fail(job.id, "boom", max_attempts=5)
    assert outcome == "dead"
    with get_engine(test_db_url).connect() as c:
        assert c.execute(text("SELECT status FROM job")).scalar() == "dead"


def test_expired_lease_is_reclaimed(q, test_db_url):
    _enqueue(q, test_db_url, 1)
    job = q.claim("w1", lease_seconds=60)
    assert q.claim("w2") is None
    with get_engine(test_db_url).begin() as c:
        c.execute(text("UPDATE job SET locked_until = now() - interval '1 second'"))
    again = q.claim("w2")
    assert again is not None and again.id == job.id and again.attempts == 2
