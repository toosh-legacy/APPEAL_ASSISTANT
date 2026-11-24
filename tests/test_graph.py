"""LangGraph orchestration: interrupts for human input, the revision loop, checkpointing, approval."""

from __future__ import annotations

import pytest
from test_pipeline import _gold_coded, client, confirm, create, drain  # noqa: F401  (client is a fixture)

pytestmark = pytest.mark.full


def _state(cid):
    from appeal_worker.orchestrator import Orchestrator

    return Orchestrator().graph.get_state({"configurable": {"thread_id": cid}})


def test_graph_pauses_for_fact_confirmation_and_resumes(client):  # noqa: F811
    cid, H = create(client, _gold_coded(1)["text"])
    drain()
    st = _state(cid)
    assert st.next == ("confirm_facts",)
    assert [i.value["type"] for t in st.tasks for i in t.interrupts] == ["confirm_facts"]
    assert client.get(f"/v1/cases/{cid}", headers=H).json()["status"] == "AWAITING_CONFIRMATION"
    confirm(client, cid, H)
    drain()
    assert client.get(f"/v1/cases/{cid}", headers=H).json()["status"] == "READY"
    assert _state(cid).next == ()


def test_reviewer_rejections_loop_back_to_the_writer_then_pause_for_a_person(client, monkeypatch):  # noqa: F811
    from appeal_core.schemas import Issue, Review
    from appeal_worker import agents

    cid, H = create(client, _gold_coded(2)["text"])
    drain()
    confirm(client, cid, H)
    real_write, writes = agents.write, []

    def counting_write(*a, **k):
        writes.append(k.get("revision"))
        return real_write(*a, **k)

    monkeypatch.setattr(agents, "write", counting_write)
    monkeypatch.setattr(agents, "review", lambda *a, **k: Review(blocking_issues=[Issue(code="unsupported", message="test")], score=0.0))
    drain()
    assert writes == [0, 1, 2]  # first draft + max_revisions (2) rewrites
    assert client.get(f"/v1/cases/{cid}", headers=H).json()["status"] == "NEEDS_HUMAN"
    st = _state(cid)
    assert [i.value["type"] for t in st.tasks for i in t.interrupts] == ["needs_human"]
    monkeypatch.undo()
    r = client.post(f"/v1/cases/{cid}/approve", headers=H)
    assert r.status_code == 200, r.text
    drain()
    assert client.get(f"/v1/cases/{cid}", headers=H).json()["status"] == "READY"


def test_approve_is_only_for_cases_waiting_on_a_person(client):  # noqa: F811
    cid, H = create(client, _gold_coded(3)["text"])
    drain()
    assert client.post(f"/v1/cases/{cid}/approve", headers=H).status_code == 409


def test_checkpoints_are_stored_in_postgres(client):  # noqa: F811
    from appeal_core.db import get_engine
    from sqlalchemy import text

    cid, _ = create(client, _gold_coded(4)["text"])
    drain()
    with get_engine().connect() as c:
        n = c.execute(text("select count(*) from checkpoints where thread_id = :t"), {"t": cid}).scalar()
    assert n and n >= 2


def test_lite_mode_uses_sqlite_checkpoints():
    from appeal_worker.graph import build_graph, checkpointer_for
    from langgraph.checkpoint.sqlite import SqliteSaver

    saver = checkpointer_for("sqlite:///var/app.db")
    assert isinstance(saver, SqliteSaver)
    assert build_graph(object(), saver).checkpointer is saver
