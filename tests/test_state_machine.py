import itertools

import pytest
from appeal_core.models import Case
from appeal_core.state_machine import (
    EDGES,
    TRANSITIONS,
    ConcurrencyConflict,
    IllegalTransition,
    Status,
    can_transition,
    check,
    transition,
)

ALL = list(Status)


def test_spec_edges_present():
    expected = {
        ("RECEIVED", "EXTRACTING"),
        ("EXTRACTING", "AWAITING_CONFIRMATION"),
        ("EXTRACTING", "FAILED"),
        ("AWAITING_CONFIRMATION", "CLASSIFYING"),
        ("CLASSIFYING", "NEEDS_CATEGORY"),
        ("NEEDS_CATEGORY", "RESEARCHING"),
        ("CLASSIFYING", "RESEARCHING"),
        ("RESEARCHING", "DRAFTING"),
        ("DRAFTING", "REVIEWING"),
        ("REVIEWING", "DRAFTING"),
        ("REVIEWING", "NEEDS_HUMAN"),
        ("REVIEWING", "READY"),
        ("NEEDS_HUMAN", "READY"),
    }
    assert {(a.value, b.value) for a, b in EDGES} == expected


@pytest.mark.parametrize("src,dst", EDGES)
def test_every_legal_edge(src, dst):
    check(src, dst)
    assert can_transition(src, dst)


@pytest.mark.parametrize("src,dst", [(a, b) for a, b in itertools.product(ALL, ALL) if b not in TRANSITIONS[a]])
def test_every_illegal_pair_raises(src, dst):
    with pytest.raises(IllegalTransition):
        check(src, dst)


@pytest.mark.full
@pytest.mark.parametrize("src,dst", EDGES)
def test_every_edge_through_domain_service(db_session, src, dst):
    c = Case(status=src.value)
    db_session.add(c)
    db_session.flush()
    transition(db_session, c, dst)
    assert c.status == dst.value


@pytest.mark.full
def test_illegal_transition_through_domain_service(db_session):
    c = Case(status="READY")
    db_session.add(c)
    db_session.flush()
    with pytest.raises(IllegalTransition):
        transition(db_session, c, Status.DRAFTING)


@pytest.mark.full
def test_optimistic_concurrency(db_session):
    c = Case(status="AWAITING_CONFIRMATION")
    db_session.add(c)
    db_session.flush()
    v = c.version
    with pytest.raises(ConcurrencyConflict):
        transition(db_session, c, Status.CLASSIFYING, expected_version=v + 7)
    transition(db_session, c, Status.CLASSIFYING, expected_version=v)
    assert c.version == v + 1
