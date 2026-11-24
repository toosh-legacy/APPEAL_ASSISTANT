"""Case orchestrator: a LangGraph StateGraph (graph.py) whose nodes are the steps below (SPEC 8.2, ADR-03).

Each step is keyed by (case_id, agent, input_hash). The step's output row (agent_run) and the case's
state transition are committed in ONE transaction, so after a crash either both happened or neither did.
On redelivery the pipeline replays from the top: completed steps return their stored output without
calling any provider, and work resumes at the first step that has no checkpoint.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from appeal_core.adapters import get_blob_store, get_progress_bus, get_queue, get_text_extractor
from appeal_core.db import must_get, must_scalar, session_factory
from appeal_core.extract_text import UnsupportedDocument
from appeal_core.llm.base import CALL_LOG
from appeal_core.models import AgentRun, Case, Citation, Deadline, Document, Extraction, Letter, TokenVault
from appeal_core.privacy.vault import TokenMap, decrypt, encrypt, rehydrate, unwrap
from appeal_core.schemas import Classification, LetterDraft, Research, Review
from appeal_core.settings import get_settings
from appeal_core.state_machine import Status, transition
from appeal_core.telemetry import get_logger, span
from sqlalchemy import select
from sqlalchemy.orm import Session

from appeal_worker import agents

log = get_logger("orchestrator")


def input_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


class StepFailed(Exception):
    pass


class CaseBusy(Exception):
    """Another worker holds this case's lock; the job is retried later (per-case ordering, like Service Bus sessions)."""


class Orchestrator:
    def __init__(self, url: str | None = None, retriever=None, bus=None):
        self.url = url
        self.Session = session_factory(url)
        self._retriever = retriever
        self.bus = bus or get_progress_bus()
        self.provider_calls = 0  # for resilience tests
        self._graph: Any = None

    @property
    def retriever(self):
        if self._retriever is None:
            from appeal_core.retrieval.retriever import get_retriever

            self._retriever = get_retriever(url=self.url)
        return self._retriever

    # ------------------------------------------------------------------ helpers
    def publish(self, case_id: str, **event: Any) -> None:
        try:
            self.bus.publish(case_id, {"at": datetime.now(UTC).isoformat(), **event})
        except Exception as e:  # progress is best-effort; the DB is the source of truth
            log.warning("progress publish failed", extra={"error": type(e).__name__})

    def _cached(self, s: Session, case_id: str, agent: str, h: str) -> AgentRun | None:
        return s.scalar(select(AgentRun).where(AgentRun.case_id == case_id, AgentRun.agent == agent, AgentRun.input_hash == h, AgentRun.status == "ok"))

    def step(
        self,
        case_id: str,
        agent: str,
        inp: Any,
        fn: Callable[[], dict],
        pre: set[Status],
        next_status: Callable[[dict], Status | None],
        on_commit: Callable[[Session, Case, dict], None] | None = None,
    ) -> dict:
        h = input_hash(inp)
        with self.Session() as s:
            row = self._cached(s, case_id, agent, h)
            if row is not None:
                return dict(row.output or {})
            case = must_get(s, Case, case_id)
            if Status(case.status) not in pre:
                raise StepFailed(f"{agent}: case in {case.status}, expected one of {sorted(pre)}")
        n0 = len(CALL_LOG.records)
        t0 = time.perf_counter()
        with span(f"agent.{agent}", case_id=case_id):
            out = fn()
        latency = int((time.perf_counter() - t0) * 1000)
        recs = CALL_LOG.records[n0:]
        self.provider_calls += len(recs)
        with self.Session.begin() as s:
            case = must_get(s, Case, case_id)
            s.add(
                AgentRun(
                    case_id=case_id,
                    agent=agent,
                    input_hash=h,
                    output=out,
                    prompt_id=recs[-1].prompt_id if recs else None,
                    prompt_version=recs[-1].prompt_version if recs else None,
                    provider=recs[-1].provider if recs else "local",
                    model=recs[-1].model if recs else None,
                    tokens_in=sum(r.tokens_in for r in recs),
                    tokens_out=sum(r.tokens_out for r in recs),
                    cost_usd=sum(r.cost_usd for r in recs),
                    latency_ms=latency,
                    status="ok",
                )
            )
            if on_commit:
                on_commit(s, case, out)
            nxt = next_status(out)
            if nxt is not None:
                transition(s, case, nxt, actor=f"agent:{agent}")
            new_status = case.status
        self.publish(case_id, type="step", agent=agent, status=new_status, latency_ms=latency)
        return out

    def _vault(self, s: Session, case_id: str) -> tuple[bytes, TokenMap]:
        return vault_keys(s, case_id)

    # ------------------------------------------------------------------ LangGraph
    @property
    def graph(self):
        if self._graph is None:
            from appeal_worker.graph import build_graph, checkpointer_for

            self._graph = build_graph(self, checkpointer_for(self.url))
        return self._graph

    # ------------------------------------------------------------------ job entry
    def handle(self, topic: str, case_id: str, carrier: dict | None = None) -> None:
        from appeal_core.db import get_engine
        from sqlalchemy import text

        key = int(hashlib.sha256(case_id.encode()).hexdigest()[:15], 16)
        with get_engine(self.url).connect() as lock_conn:
            if not lock_conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}).scalar():
                raise CaseBusy(case_id)
            try:
                with span(f"job.{topic}", carrier=carrier, topic=topic, case_id=case_id):
                    if topic not in ("case.ingest", "case.draft", "case.approve"):
                        raise ValueError(f"unknown topic {topic}")
                    self.run_graph(case_id, topic)
            finally:
                lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
                lock_conn.commit()

    def run_graph(self, case_id: str, topic: str) -> None:
        """One LangGraph thread per case. A graph paused for human input resumes with Command(resume=...);
        a graph that stopped mid-step (worker killed) continues from its last checkpoint; otherwise it starts
        from the top, where completed steps replay from their agent_run rows without calling a provider."""
        from langgraph.types import Command

        cfg: Any = {"configurable": {"thread_id": case_id}}
        g = self.graph
        st = g.get_state(cfg)
        if st.next and any(t.interrupts for t in st.tasks):
            g.invoke(Command(resume={"topic": topic}), cfg, durability="sync")
        elif st.next:
            g.invoke(None, cfg, durability="sync")
        else:
            g.invoke({"case_id": case_id, "revision": 0, "drops": []}, cfg, durability="sync")
            st = g.get_state(cfg)
            if topic == "case.approve" and any(i.value.get("type") == "needs_human" for t in st.tasks for i in t.interrupts):
                g.invoke(Command(resume={"topic": topic}), cfg, durability="sync")  # replayed up to the pause: deliver the approval
        self.publish(case_id, type="status", status=self.status(case_id))

    def status(self, case_id: str) -> str:
        with self.Session() as s:
            return must_get(s, Case, case_id).status

    # ------------------------------------------------------------------ nodes (wired in graph.py)
    def node_intake(self, case_id: str) -> bool:
        """Returns False when the document cannot be read (case FAILED)."""
        with self.Session.begin() as s:
            case = must_get(s, Case, case_id)
            if case.status == Status.RECEIVED:
                transition(s, case, Status.EXTRACTING, actor="worker")
                self.publish(case_id, type="status", status=Status.EXTRACTING.value)
            elif case.status == Status.FAILED:
                return False
            elif case.status != Status.EXTRACTING:
                return True  # already past intake
            doc = must_scalar(s, select(Document).where(Document.case_id == case_id), "document")
            doc_key = {"doc": doc.id, "sha": doc.sha256}

        def run_intake() -> dict:
            with self.Session() as s:
                doc: Document = must_scalar(s, select(Document).where(Document.case_id == case_id), "document")
                v = must_get(s, TokenVault, case_id)
                dk = unwrap(v.wrapped_data_key)
                if doc.text_encrypted is not None:
                    raw = decrypt(dk, doc.text_encrypted, "document")
                else:
                    if not doc.blob_uri:
                        raise UnsupportedDocument("document has neither text nor an uploaded file")
                    data = get_blob_store().get(doc.blob_uri.split("/", 1)[1])
                    raw, pages = get_text_extractor().extract(data, doc.blob_uri)
            ext, tokenized, tmap = agents.intake(raw)
            return {"extracted": ext.model_dump(), "tokenized": tokenized, "tmap": encrypt(dk, tmap.to_json(), "tokenmap").hex()}

        def save(s: Session, case: Case, out: dict) -> None:
            v = must_get(s, TokenVault, case_id)
            v.encrypted_map = bytes.fromhex(out["tmap"])
            ext = out["extracted"]
            fields = {k: fv["value"] for k, fv in ext["fields"].items()}
            conf = {k: {"confidence": fv["confidence"], "hint": fv.get("hint")} for k, fv in ext["fields"].items()}
            row = s.scalar(select(Extraction).where(Extraction.case_id == case_id))
            if row is None:
                row = Extraction(case_id=case_id)
                s.add(row)
            row.fields, row.field_confidence = fields, conf
            row.redacted_text = out["tokenized"]
            row.injection = {"flags": ext.get("injection_flags", [])}
            case.plan_type, case.state = ext.get("plan_type"), ext.get("state")

        try:
            self.step(case_id, "intake", doc_key, run_intake, {Status.EXTRACTING}, lambda o: Status.AWAITING_CONFIRMATION, save)
        except UnsupportedDocument as e:
            with self.Session.begin() as s:
                case = must_get(s, Case, case_id)
                case.error = str(e)
                transition(s, case, Status.FAILED, actor="worker")
            self.publish(case_id, type="status", status="FAILED", message=str(e))
            return False
        return True

    def _facts(self, case_id: str) -> tuple[dict, TokenMap, bytes, list[str]]:
        with self.Session() as s:
            facts, tmap, dk, flags = self.facts_for(s, case_id)
        with self.Session.begin() as s:  # persist new tokens created from corrections
            v = must_get(s, TokenVault, case_id)
            v.encrypted_map = encrypt(dk, tmap.to_json(), "tokenmap")
        return facts, tmap, dk, flags

    def node_classify(self, case_id: str) -> bool:
        """Returns True when the user must choose the category (case NEEDS_CATEGORY)."""
        facts, tmap, _, _ = self._facts(case_id)
        reason: str | None = facts.get("denial_reason")
        codes: list[str] = list(facts.get("denial_codes") or [])
        service: str | None = facts.get("service")
        raw = tmap.raw_values()
        with self.Session() as s:
            letter = s.scalar(select(Extraction.redacted_text).where(Extraction.case_id == case_id))

        def set_cat(s: Session, case: Case, out: dict) -> None:
            if not out["needs_user"]:
                case.category = out["category"]

        cls = Classification(
            **self.step(
                case_id,
                "classifier",
                {"reason": reason, "codes": codes, "service": service},
                lambda: agents.classify(reason, codes, service, raw_values=raw, letter=letter).model_dump(),
                {Status.CLASSIFYING},
                lambda o: Status.NEEDS_CATEGORY if o["needs_user"] else Status.RESEARCHING,
                set_cat,
            )
        )
        if self.status(case_id) == Status.NEEDS_CATEGORY:
            self.publish(case_id, type="needs_category", status=Status.NEEDS_CATEGORY.value, suggestion=cls.category, alternatives=cls.alternatives)
            return True
        return False

    def node_research(self, case_id: str) -> dict:
        facts, _, _, _ = self._facts(case_id)
        with self.Session() as s:
            case = must_get(s, Case, case_id)
            cls_out = s.scalar(select(AgentRun.output).where(AgentRun.case_id == case_id, AgentRun.agent == "classifier").order_by(AgentRun.created_at.desc()).limit(1)) or {}
            category: str = case.category or cls_out.get("category", "other_unclear")
            plan_type: str | None = case.plan_type or facts.get("plan_type")
        service: str | None = facts.get("service")
        reason: str | None = facts.get("denial_reason")
        notice: str | None = facts.get("notice_date")
        r_in = {"category": category, "plan_type": plan_type, "service": service, "reason": reason, "notice_date": notice}
        out = self.step(
            case_id,
            "research",
            r_in,
            lambda: agents.research(category, plan_type, service, reason, notice, self.retriever).model_dump(),
            {Status.RESEARCHING},
            lambda o: Status.DRAFTING,
        )
        return {"category": category, "research": out}

    def node_write(self, case_id: str, category: str, research: dict, revision: int, drops: list[str]) -> dict:
        facts, tmap, _, _ = self._facts(case_id)
        res = Research(**research)
        w_in = {"facts": facts, "category": category, "research": input_hash(research), "rev": revision, "drops": drops}
        return self.step(
            case_id,
            "writer",
            w_in,
            lambda: agents.write(facts, category, res, tmap.raw_values(), revision=revision, drop=drops).model_dump(),
            {Status.DRAFTING},
            lambda o: Status.REVIEWING,
            lambda s, c, o: setattr(c, "degraded", bool(o.get("degraded")) or c.degraded),
        )

    def node_review(self, case_id: str, research: dict, draft_out: dict, revision: int) -> tuple[str, list[str]]:
        """Returns (verdict, rewrite instructions); verdict is ready | revise | needs_human."""
        facts, tmap, dk, flags = self._facts(case_id)
        res, draft = Research(**research), LetterDraft(**draft_out)
        last = revision >= get_settings().max_revisions

        def decide(o: dict) -> Status:
            if not o["blocking_issues"]:
                return Status.READY
            return Status.NEEDS_HUMAN if last else Status.DRAFTING

        def finalize(s: Session, case: Case, o: dict) -> None:
            if not o["blocking_issues"] or last:
                self._store_letter(s, case, draft, Review(**o), res, tmap, dk)

        rv = Review(
            **self.step(
                case_id,
                "reviewer",
                {"draft": draft_out, "research": input_hash(research)},
                lambda: agents.review(draft, res, facts, set(tmap.tokens), flags, tmap.raw_values()).model_dump(),
                {Status.REVIEWING},
                decide,
                finalize,
            )
        )
        if not rv.blocking_issues:
            return "ready", []
        if last:
            return "needs_human", []
        return "revise", agents.drops_from_review(draft, rv)

    def node_approve(self, case_id: str) -> None:
        """A person reviewed the NEEDS_HUMAN letter and approved it."""
        with self.Session.begin() as s:
            case = must_get(s, Case, case_id)
            if case.status == Status.NEEDS_HUMAN:
                transition(s, case, Status.READY, actor="user")

    def facts_for(self, s: Session, case_id: str) -> tuple[dict, TokenMap, bytes, list[str]]:
        return facts_for(s, case_id)

    def _store_letter(self, s: Session, case: Case, draft: LetterDraft, rv: Review, res: Research, tmap: TokenMap, dk: bytes) -> None:
        body = render_text(draft, tmap)
        n = (s.scalar(select(Letter.version).where(Letter.case_id == case.id).order_by(Letter.version.desc()).limit(1)) or 0) + 1
        s.add(
            Letter(
                case_id=case.id,
                version=n,
                body_encrypted=encrypt(dk, body, "letter"),
                sentences=draft.model_dump()["sections"],
                placeholders_remaining=len(draft.placeholders),
                review_score=rv.score,
                review=rv.model_dump(),
            )
        )
        used = {c for sec in draft.sections for sen in sec.sentences for c in sen.citations}
        for r in res.rules:
            s.add(Citation(case_id=case.id, cite_id=r.cite_id, chunk_id=r.chunk_id, kind="R", score=r.score, used_in_letter=r.cite_id in used))
        for p in res.precedents:
            s.add(Citation(case_id=case.id, cite_id=p.cite_id, chunk_id=p.chunk_id, kind="P", score=p.score, used_in_letter=p.cite_id in used))
        for d in res.deadlines:
            s.add(Deadline(case_id=case.id, kind=d.kind, due_date=datetime.fromisoformat(d.due_date).date(), rule_id=d.rule_id, basis_chunk_id=d.basis_chunk_id))
        now = datetime.now(UTC)
        for doc in s.scalars(select(Document).where(Document.case_id == case.id)):
            doc.retention_until = now + timedelta(days=1)  # upload scheduled for deletion
        case.expires_at = now + timedelta(days=30)


def render_text(draft: LetterDraft, tmap: TokenMap | None) -> str:
    out = []
    for sec in draft.sections:
        if sec.id in ("header", "closing"):
            out.append("\n".join(s.text for s in sec.sentences))
        else:
            out.append(" ".join(s.text + "".join(f" [{c}]" for c in s.citations) for s in sec.sentences))
    text = "\n\n".join(out)
    return rehydrate(text, tmap) if tmap else text


def run_worker(stop_after_idle: float | None = None, worker_id: str = "worker-1", url: str | None = None, poll: float = 0.5) -> None:
    q = get_queue()
    orch = Orchestrator(url=url)
    idle = 0.0
    settings = get_settings()
    while True:
        job = q.claim(worker_id)
        if job is None:
            time.sleep(poll)
            idle += poll
            if stop_after_idle is not None and idle >= stop_after_idle:
                return
            continue
        idle = 0.0
        try:
            orch.handle(job.topic, job.case_id, (job.payload or {}).get("trace"))
            q.complete(job.id)
        except Exception as e:
            outcome = q.fail(job.id, f"{type(e).__name__}: {e}", settings.job_max_attempts)
            log.error("job failed", extra={"job_id": job.id, "topic": job.topic, "outcome": outcome, "error": type(e).__name__})


def vault_keys(s: Session, case_id: str) -> tuple[bytes, TokenMap]:
    """The case's unwrapped data key and decrypted token map."""
    v = must_get(s, TokenVault, case_id)
    dk = unwrap(v.wrapped_data_key)
    return dk, TokenMap.from_json(decrypt(dk, v.encrypted_map, "tokenmap"))


def facts_for(s: Session, case_id: str) -> tuple[dict, TokenMap, bytes, list[str]]:
    """Confirmed facts (user corrections applied, identifiers tokenized), token map, data key, injection flags."""
    ex = must_scalar(s, select(Extraction).where(Extraction.case_id == case_id), "extraction")
    dk, tmap = vault_keys(s, case_id)
    facts = dict(ex.fields)
    facts.update({k: v for k, v in (ex.user_corrections or {}).items() if v not in (None, "")})
    person = next((t for t in tmap.tokens if t.startswith("[PERSON_")), None)
    facts["member_name"] = person
    if isinstance(facts.get("denial_codes"), str):
        facts["denial_codes"] = [c.strip() for c in facts["denial_codes"].split(",") if c.strip()]
    # any raw identifier typed in a correction is tokenized before it can reach a model
    for k, v in list(facts.items()):
        if isinstance(v, str) and k in ("member_id", "claim_number") and not v.startswith("["):
            facts[k] = tmap.token_for(k.upper(), v)
    return facts, tmap, dk, (ex.injection or {}).get("flags", [])
