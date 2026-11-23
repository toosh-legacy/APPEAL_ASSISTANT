"""Case state machine (SPEC 7.5). All transitions go through `transition()`; optimistic concurrency via
the `version` column (SQLAlchemy version_id_col raises StaleDataError on a lost update)."""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import update
from sqlalchemy.orm import Session

from appeal_core.models import AuditEvent, Case


class Status(StrEnum):
    RECEIVED = "RECEIVED"
    EXTRACTING = "EXTRACTING"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    CLASSIFYING = "CLASSIFYING"
    NEEDS_CATEGORY = "NEEDS_CATEGORY"
    RESEARCHING = "RESEARCHING"
    DRAFTING = "DRAFTING"
    REVIEWING = "REVIEWING"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    READY = "READY"
    FAILED = "FAILED"


S = Status
TRANSITIONS: dict[Status, set[Status]] = {
    S.RECEIVED: {S.EXTRACTING},
    S.EXTRACTING: {S.AWAITING_CONFIRMATION, S.FAILED},
    S.AWAITING_CONFIRMATION: {S.CLASSIFYING},
    S.CLASSIFYING: {S.NEEDS_CATEGORY, S.RESEARCHING},
    S.NEEDS_CATEGORY: {S.RESEARCHING},
    S.RESEARCHING: {S.DRAFTING},
    S.DRAFTING: {S.REVIEWING},
    S.REVIEWING: {S.DRAFTING, S.NEEDS_HUMAN, S.READY},
    S.NEEDS_HUMAN: {S.READY},
    S.READY: set(),
    S.FAILED: set(),
}
EDGES = [(a, b) for a, bs in TRANSITIONS.items() for b in sorted(bs)]


class IllegalTransition(Exception):
    def __init__(self, src: str, dst: str):
        super().__init__(f"illegal transition {src} -> {dst}")
        self.src, self.dst = src, dst


class ConcurrencyConflict(Exception):
    pass


def can_transition(src: str, dst: str) -> bool:
    return Status(dst) in TRANSITIONS[Status(src)]


def check(src: str, dst: str) -> None:
    if not can_transition(src, dst):
        raise IllegalTransition(src, dst)


def transition(session: Session, case: Case, dst: Status | str, actor: str = "system", expected_version: int | None = None) -> Case:
    """Move a case to `dst`. If `expected_version` is given, the update only applies if the row still
    has that version (compare-and-swap), else ConcurrencyConflict."""
    dst = Status(dst)
    check(case.status, dst)
    if expected_version is not None:
        res = session.execute(
            update(Case)
            .where(Case.id == case.id, Case.version == expected_version)
            .values(status=dst.value, version=expected_version + 1)
            .execution_options(synchronize_session=False)
        )
        if res.rowcount != 1:
            raise ConcurrencyConflict(f"case {case.id} changed (expected version {expected_version})")
        session.refresh(case)
    else:
        case.status = dst.value
        session.flush()
    session.add(AuditEvent(actor=actor, action=f"transition:{dst.value}", entity=f"case:{case.id}"))
    return case
