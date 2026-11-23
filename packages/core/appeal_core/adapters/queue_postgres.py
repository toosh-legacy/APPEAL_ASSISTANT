"""Postgres job queue + transactional outbox.

`enqueue` is called inside the caller's transaction (same commit as the state change) — that is the
outbox pattern: the job row exists if and only if the state change committed.
`claim` uses SELECT ... FOR UPDATE SKIP LOCKED so many workers can claim different jobs safely.
Expired leases (crashed worker) are re-claimable. Failures retry with exponential backoff + jitter;
after max attempts the job is dead-lettered (status='dead').
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text

from appeal_core.db import get_engine
from appeal_core.interfaces import ClaimedJob
from appeal_core.models import Job


class PostgresJobQueue:
    def __init__(self, url: str | None = None):
        self.url = url

    def enqueue(self, session: Any, topic: str, payload: dict[str, Any], case_id: str | None = None) -> int:
        job = Job(topic=topic, payload=payload, case_id=case_id, status="ready")
        session.add(job)
        session.flush()
        return int(job.id)

    def claim(self, worker_id: str, lease_seconds: int = 60) -> ClaimedJob | None:
        eng = get_engine(self.url)
        with eng.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT id FROM job
                    WHERE (status = 'ready' AND available_at <= now())
                       OR (status = 'running' AND locked_until < now())
                    ORDER BY available_at, id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                    """
                )
            ).first()
            if row is None:
                return None
            r = conn.execute(
                text(
                    """
                    UPDATE job SET status='running', attempts = attempts + 1, locked_by=:w,
                           locked_until = now() + make_interval(secs => :lease)
                    WHERE id=:id
                    RETURNING id, topic, payload, case_id, attempts
                    """
                ),
                {"w": worker_id, "lease": lease_seconds, "id": row.id},
            ).first()
        return ClaimedJob(id=r.id, topic=r.topic, payload=r.payload, case_id=r.case_id, attempts=r.attempts)

    def extend(self, job_id: int, lease_seconds: int = 60) -> None:
        with get_engine(self.url).begin() as conn:
            conn.execute(
                text("UPDATE job SET locked_until = now() + make_interval(secs => :l) WHERE id=:id"),
                {"l": lease_seconds, "id": job_id},
            )

    def complete(self, job_id: int) -> None:
        with get_engine(self.url).begin() as conn:
            conn.execute(text("UPDATE job SET status='done', locked_by=NULL, locked_until=NULL WHERE id=:id"), {"id": job_id})

    def fail(self, job_id: int, error: str, max_attempts: int = 5) -> str:
        with get_engine(self.url).begin() as conn:
            attempts = conn.execute(text("SELECT attempts FROM job WHERE id=:id"), {"id": job_id}).scalar_one()
            if attempts >= max_attempts:
                conn.execute(
                    text("UPDATE job SET status='dead', last_error=:e, locked_by=NULL, locked_until=NULL WHERE id=:id"),
                    {"e": error[:2000], "id": job_id},
                )
                return "dead"
            delay = min(60.0, (2 ** (attempts - 1)) * 0.5) + random.random() * 0.25
            conn.execute(
                text(
                    "UPDATE job SET status='ready', last_error=:e, locked_by=NULL, locked_until=NULL, available_at=:at WHERE id=:id"
                ),
                {"e": error[:2000], "id": job_id, "at": datetime.now(UTC) + timedelta(seconds=delay)},
            )
            return "retry"
