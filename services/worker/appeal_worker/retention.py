"""Retention purge (`make retention`; an Azure Functions timer trigger in Phase C).

- Uploads (documents) past `retention_until`: delete the blob and the stored text.
- Cases past `expires_at`: delete the case (cascades to vault, letters, agent runs, ...).
Deleting a case's token vault destroys its wrapped data key, so any remaining ciphertext is unreadable.
"""

from __future__ import annotations

from datetime import UTC, datetime

from appeal_core.adapters import get_blob_store
from appeal_core.db import session_scope
from appeal_core.models import AuditEvent, Case, Document
from sqlalchemy import select


def purge(now: datetime | None = None, url: str | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    blobs = docs = cases = 0
    with session_scope(url) as s:
        for d in s.scalars(select(Document).where(Document.retention_until.is_not(None), Document.retention_until < now)):
            if d.blob_uri:
                try:
                    get_blob_store().delete(d.blob_uri.split("/", 1)[1])
                    blobs += 1
                except Exception:
                    pass
                d.blob_uri = None
            if d.text_encrypted is not None:
                d.text_encrypted = None
            d.retention_until = None
            docs += 1
            s.add(AuditEvent(actor="retention", action="document.purge", entity=f"case:{d.case_id}"))
        for c in s.scalars(select(Case).where(Case.expires_at.is_not(None), Case.expires_at < now)):
            s.add(AuditEvent(actor="retention", action="case.expire", entity=f"case:{c.id}"))
            s.delete(c)
            cases += 1
    return {"documents_purged": docs, "blobs_deleted": blobs, "cases_deleted": cases}


if __name__ == "__main__":
    print(purge())
