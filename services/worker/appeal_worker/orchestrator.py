"""Persisted state-machine orchestrator (SPEC 8.2, ADR-03).

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
from appeal_core.db import session_factory
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
                return row.output
            case = s.get(Case, case_id)
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
            case = s.get(Case, case_id)
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
        v = s.get(TokenVault, case_id)
        dk = unwrap(v.wrapped_data_key)
        return dk, TokenMap.from_json(decrypt(dk, v.encrypted_map, "tokenmap"))

    # ------------------------------------------------------------------ job entry
    def handle(self, topic: str, case_id: str) -> None:
        from sqlalchemy import text

        from appeal_core.db import get_engine

        key = int(hashlib.sha256(case_id.encode()).hexdigest()[:15], 16)
        with get_engine(self.url).connect() as lock_conn:
            if not lock_conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}).scalar():
                raise CaseBusy(case_id)
            try:
                with span("job", topic=topic, case_id=case_id):
                    if topic == "case.ingest":
                        self.ingest(case_id)
                    elif topic == "case.draft":
                        self.draft(case_id)
                    else:
                        raise ValueError(f"unknown topic {topic}")
            finally:
                lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
                lock_conn.commit()

    # ------------------------------------------------------------------ ingest
    def ingest(self, case_id: str) -> None:
        with self.Session.begin() as s:
            case = s.get(Case, case_id)
            if case.status == Status.RECEIVED:
                transition(s, case, Status.EXTRACTING, actor="worker")
                self.publish(case_id, type="status", status=Status.EXTRACTING.value)
            elif case.status != Status.EXTRACTING:
                return  # already past intake
            doc = s.scalar(select(Document).where(Document.case_id == case_id))
            doc_key = {"doc": doc.id, "sha": doc.sha256}

        def run_intake() -> dict:
            with self.Session() as s:
                doc = s.scalar(select(Document).where(Document.case_id == case_id))
                v = s.get(TokenVault, case_id)
                dk = unwrap(v.wrapped_data_key)
                if doc.text_encrypted is not None:
                    raw = decrypt(dk, doc.text_encrypted, "document")
                else:
                    data = get_blob_store().get(doc.blob_uri.split("/", 1)[1])
                    raw, pages = get_text_extractor().extract(data, doc.blob_uri)
            ext, tokenized, tmap = agents.intake(raw)
            return {"extracted": ext.model_dump(), "tokenized": tokenized, "tmap": encrypt(dk, tmap.to_json(), "tokenmap").hex()}

        def save(s: Session, case: Case, out: dict) -> None:
            v = s.get(TokenVault, case_id)
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
                case = s.get(Case, case_id)
                case.error = str(e)
                transition(s, case, Status.FAILED, actor="worker")
            self.publish(case_id, type="status", status="FAILED", message=str(e))

    # ------------------------------------------------------------------ draft
    def facts_for(self, s: Session, case_id: str) -> tuple[dict, TokenMap, bytes, list[str]]:
        ex = s.scalar(select(Extraction).where(Extraction.case_id == case_id))
        dk, tmap = self._vault(s, case_id)
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

    def draft(self, case_id: str) -> None:
        settings = get_settings()
        with self.Session() as s:
            facts, tmap, dk, flags = self.facts_for(s, case_id)
        # persist new tokens created from corrections
        with self.Session.begin() as s:
            v = s.get(TokenVault, case_id)
            v.encrypted_map = encrypt(dk, tmap.to_json(), "tokenmap")
        raw_values = tmap.raw_values()

        cls_in = {"reason": facts.get("denial_reason"), "codes": facts.get("denial_codes") or [], "service": facts.get("service")}

        def set_cat(s: Session, case: Case, out: dict) -> None:
            if not out["needs_user"]:
                case.category = out["category"]

        cls = Classification(
            **self.step(
                case_id,
                "classifier",
                cls_in,
                lambda: agents.classify(cls_in["reason"], cls_in["codes"], cls_in["service"]).model_dump(),
                {Status.CLASSIFYING},
                lambda o: Status.NEEDS_CATEGORY if o["needs_user"] else Status.RESEARCHING,
                set_cat,
            )
        )
        with self.Session() as s:
            case = s.get(Case, case_id)
            if case.status == Status.NEEDS_CATEGORY:
                self.publish(case_id, type="needs_category", status=case.status, suggestion=cls.category, alternatives=cls.alternatives)
                return
            category = case.category or cls.category
            plan_type = case.plan_type or facts.get("plan_type")

        r_in = {"category": category, "plan_type": plan_type, "service": facts.get("service"), "reason": facts.get("denial_reason"), "notice_date": facts.get("notice_date")}
        res = Research(
            **self.step(
                case_id,
                "research",
                r_in,
                lambda: agents.research(r_in["category"], r_in["plan_type"], r_in["service"], r_in["reason"], r_in["notice_date"], self.retriever).model_dump(),
                {Status.RESEARCHING},
                lambda o: Status.DRAFTING,
            )
        )
        known = set(tmap.tokens)
        drops: list[str] = []
        for rev in range(settings.max_revisions + 1):
            w_in = {"facts": facts, "category": category, "research": input_hash(res.model_dump()), "rev": rev, "drops": drops}
            draft = LetterDraft(
                **self.step(
                    case_id,
                    "writer",
                    w_in,
                    lambda: agents.write(facts, category, res, raw_values, revision=rev, drop=drops).model_dump(),
                    {Status.DRAFTING},
                    lambda o: Status.REVIEWING,
                    lambda s, c, o: setattr(c, "degraded", bool(o.get("degraded")) or c.degraded),
                )
            )
            last = rev >= settings.max_revisions

            def decide(o: dict, last=last) -> Status:
                if not o["blocking_issues"]:
                    return Status.READY
                return Status.NEEDS_HUMAN if last else Status.DRAFTING

            def finalize(s: Session, case: Case, o: dict, draft=draft) -> None:
                if not o["blocking_issues"] or last:
                    self._store_letter(s, case, draft, Review(**o), res, tmap, dk)

            rv = Review(
                **self.step(
                    case_id,
                    "reviewer",
                    {"draft": draft.model_dump(), "research": input_hash(res.model_dump())},
                    lambda: agents.review(draft, res, facts, known, flags).model_dump(),
                    {Status.REVIEWING},
                    decide,
                    finalize,
                )
            )
            if not rv.blocking_issues:
                break
            drops = sorted(set(drops) | set(agents.drops_from_review(draft, rv)))
        with self.Session() as s:
            st = s.get(Case, case_id).status
        self.publish(case_id, type="status", status=st)

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
            orch.handle(job.topic, job.case_id)
            q.complete(job.id)
        except Exception as e:
            outcome = q.fail(job.id, f"{type(e).__name__}: {e}", settings.job_max_attempts)
            log.error("job failed", extra={"job_id": job.id, "topic": job.topic, "outcome": outcome, "error": type(e).__name__})
