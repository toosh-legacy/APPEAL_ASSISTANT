"""The case pipeline as a LangGraph StateGraph.

    intake -> confirm_facts* -> classify -> choose_category* -> research -> write <-> review -> human_review*
                                                                                  (<= 2 rewrites)
    * pauses with interrupt() until the person acts in the web app; the API then queues a job and the worker
      resumes the thread with Command(resume=...).

One thread per case (thread_id = case id). The checkpointer stores graph state after every node: Postgres
(PostgresSaver) in full mode, SQLite (SqliteSaver) in lite mode. The `case` row stays the source of truth
for status: every node transitions it in the same transaction as its agent_run audit row, and interrupts
only happen while the case is in the matching waiting state, so the graph and the table cannot disagree.

State holds tokenized facts and public research only; raw identifiers never enter a checkpoint.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from appeal_core.llm.base import ProviderUnavailable
from appeal_core.settings import ROOT, get_settings
from appeal_core.state_machine import Status
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, interrupt
from sqlalchemy.exc import OperationalError


class CaseState(TypedDict, total=False):
    case_id: str
    failed: bool
    needs_category: bool
    category: str
    research: dict[str, Any]
    draft: dict[str, Any]
    revision: int
    drops: list[str]
    verdict: Literal["ready", "revise", "needs_human"]
    approved: bool


# transient errors only: provider outages after the gateway's own retries/fallbacks, and DB hiccups
RETRY = RetryPolicy(max_attempts=3, initial_interval=1.0, backoff_factor=2.0, jitter=True, retry_on=(ProviderUnavailable, OperationalError))


def build_graph(orch: Any, checkpointer: Any = None):
    def intake(st: CaseState) -> dict[str, Any]:
        return {"failed": not orch.node_intake(st["case_id"])}

    def confirm_facts(st: CaseState) -> dict[str, Any]:
        if orch.status(st["case_id"]) == Status.AWAITING_CONFIRMATION:
            interrupt({"type": "confirm_facts", "case_id": st["case_id"]})
        return {}

    def classify(st: CaseState) -> dict[str, Any]:
        return {"needs_category": orch.node_classify(st["case_id"])}

    def choose_category(st: CaseState) -> dict[str, Any]:
        if orch.status(st["case_id"]) == Status.NEEDS_CATEGORY:
            interrupt({"type": "choose_category", "case_id": st["case_id"]})
        return {"needs_category": False}

    def research(st: CaseState) -> dict[str, Any]:
        out = orch.node_research(st["case_id"])
        return {"category": out["category"], "research": out["research"]}

    def write(st: CaseState) -> dict[str, Any]:
        return {"draft": orch.node_write(st["case_id"], st["category"], st["research"], st.get("revision", 0), st.get("drops", []))}

    def review(st: CaseState) -> dict[str, Any]:
        rev = st.get("revision", 0)
        verdict, drops = orch.node_review(st["case_id"], st["research"], st["draft"], rev)
        if verdict == "revise":
            return {"verdict": verdict, "revision": rev + 1, "drops": sorted(set(st.get("drops", [])) | set(drops))}
        return {"verdict": verdict}

    def human_review(st: CaseState) -> dict[str, Any]:
        """Pause until the person approves the letter they reviewed (a `case.approve` job)."""
        if orch.status(st["case_id"]) != Status.NEEDS_HUMAN:
            return {"approved": True}
        got = interrupt({"type": "needs_human", "case_id": st["case_id"]})
        if (got or {}).get("topic") == "case.approve":
            orch.node_approve(st["case_id"])
            return {"approved": True}
        return {"approved": False}  # some other job woke the thread: pause again

    g: Any = StateGraph(CaseState)  # LangGraph overloads reject plain callables under mypy; runtime types are checked by tests
    g.add_node("intake", intake, retry_policy=RETRY)
    g.add_node("confirm_facts", confirm_facts)
    g.add_node("classify", classify, retry_policy=RETRY)
    g.add_node("choose_category", choose_category)
    g.add_node("research", research, retry_policy=RETRY)
    g.add_node("write", write, retry_policy=RETRY)
    g.add_node("review", review, retry_policy=RETRY)
    g.add_node("human_review", human_review)

    g.add_edge(START, "intake")
    g.add_conditional_edges("intake", lambda st: END if st.get("failed") else "confirm_facts", ["confirm_facts", END])
    g.add_edge("confirm_facts", "classify")
    g.add_conditional_edges("classify", lambda st: "choose_category" if st.get("needs_category") else "research", ["choose_category", "research"])
    g.add_edge("choose_category", "research")
    g.add_edge("research", "write")
    g.add_edge("write", "review")
    g.add_conditional_edges("review", lambda st: {"ready": END, "revise": "write", "needs_human": "human_review"}[st["verdict"]], ["write", "human_review", END])
    g.add_conditional_edges("human_review", lambda st: END if st.get("approved") else "human_review", ["human_review", END])
    return g.compile(checkpointer=checkpointer)


_SAVERS: dict[str, Any] = {}


def checkpointer_for(url: str | None = None) -> Any:
    """PostgresSaver for a Postgres DATABASE_URL (full mode), SqliteSaver for SQLite (lite mode)."""
    db = url or get_settings().database_url
    if db in _SAVERS:
        return _SAVERS[db]
    if db.startswith("sqlite"):
        import sqlite3

        from langgraph.checkpoint.sqlite import SqliteSaver

        path = ROOT / "var" / "checkpoints.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)
        saver: Any = SqliteSaver(sqlite3.connect(str(path), check_same_thread=False))
    else:
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg import Connection
        from psycopg.rows import dict_row

        conn = Connection.connect(db.replace("postgresql+psycopg://", "postgresql://"), autocommit=True, prepare_threshold=0, row_factory=dict_row)
        saver = PostgresSaver(conn)  # type: ignore[arg-type]
        # setup() creates indexes CONCURRENTLY, which blocks behind any open transaction: `make migrate` runs it
        # up front, so at runtime only call it when the tables are missing.
        have = conn.execute("SELECT to_regclass('public.checkpoint_migrations') AS t").fetchone()
        if have and have["t"] is not None:
            _SAVERS[db] = saver
            return saver
    saver.setup()
    _SAVERS[db] = saver
    return saver
