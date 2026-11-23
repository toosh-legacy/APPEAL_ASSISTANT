"""Case endpoints (SPEC 13)."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import date, datetime
from typing import Any, Literal

from appeal_core.adapters import get_blob_store, get_progress_bus, get_queue
from appeal_core.extract_text import MAX_BYTES, MAX_PASTE_CHARS
from appeal_core.kb import CATEGORIES, denial_code_descriptions, playbooks
from appeal_core.models import (
    AgentRun,
    AuditEvent,
    Case,
    Document,
    Extraction,
    KbChunk,
    Letter,
    PrecedentChunk,
    TokenVault,
)
from appeal_core.privacy.vault import TokenMap, decrypt, encrypt, new_data_key, rehydrate, unwrap
from appeal_core.schemas import Research
from appeal_core.state_machine import ConcurrencyConflict, Status, transition
from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from appeal_api.deps import Problem, TokenBucket, case_token, get_db, require_case_access

router = APIRouter(prefix="/v1")
regen_limit = TokenBucket(capacity=5, refill_per_sec=5 / 60)
create_limit = TokenBucket(capacity=20, refill_per_sec=20 / 60)
ALLOWED_UPLOADS = {".pdf": "application/pdf", ".txt": "text/plain"}


# ---------------------------------------------------------------- models
class UploadRequest(BaseModel):
    filename: str
    content_type: str
    size: int = Field(ge=1)


class UploadResponse(BaseModel):
    upload_url: str
    blob_name: str
    expires_at: datetime


class CreateCase(BaseModel):
    text: str | None = None
    blob_name: str | None = None


class CaseCreated(BaseModel):
    id: str
    status: str
    access_token: str


class Corrections(BaseModel):
    fields: dict[str, Any] = {}


class CategoryChoice(BaseModel):
    category: str


class RegenerateRequest(BaseModel):
    section_id: str
    reason: Literal["shorter", "firmer", "add_detail"]


class LetterEdit(BaseModel):
    sections: list[dict[str, Any]]


# ---------------------------------------------------------------- helpers
def _case(db: Session, case_id: str) -> Case:
    c = db.get(Case, case_id)
    if c is None:
        raise Problem(404, "Case not found")
    return c


def _vault(db: Session, case_id: str) -> tuple[bytes, TokenMap]:
    v = db.get(TokenVault, case_id)
    dk = unwrap(v.wrapped_data_key)
    return dk, TokenMap.from_json(decrypt(dk, v.encrypted_map, "tokenmap"))


def _latest(db: Session, case_id: str, agent: str) -> dict | None:
    r = db.scalar(select(AgentRun).where(AgentRun.case_id == case_id, AgentRun.agent == agent).order_by(AgentRun.created_at.desc()).limit(1))
    return r.output if r else None


def mask(value: str | None) -> str | None:
    if not value:
        return value
    v = str(value)
    return v[:4] + "•" * max(0, len(v) - 6) + v[-2:] if len(v) > 6 else "•" * len(v)


def _letter(db: Session, case_id: str) -> Letter | None:
    return db.scalar(select(Letter).where(Letter.case_id == case_id).order_by(Letter.version.desc()).limit(1))


# ---------------------------------------------------------------- uploads
@router.post("/uploads", response_model=UploadResponse)
def create_upload(req: UploadRequest) -> UploadResponse:
    ext = "." + req.filename.rsplit(".", 1)[-1].lower() if "." in req.filename else ""
    if ext not in ALLOWED_UPLOADS:
        if ext in (".png", ".jpg", ".jpeg", ".heic"):
            raise Problem(415, "Photos are coming soon", "For now, paste the letter text or upload a text PDF.")
        raise Problem(415, "Unsupported file type", "Upload a PDF or a .txt file, or paste the text.")
    if req.size > MAX_BYTES:
        raise Problem(413, "File too large", "Files can be at most 10 MB.")
    name = f"{uuid.uuid4().hex}{ext}"
    url, exp = get_blob_store().create_upload_url(name, minutes=10)
    return UploadResponse(upload_url=url, blob_name=name, expires_at=exp)


# ---------------------------------------------------------------- create
@router.post("/cases", response_model=CaseCreated, status_code=201)
def create_case(body: CreateCase, request: Request, response: Response, idempotency_key: str | None = Header(default=None), db: Session = Depends(get_db)) -> CaseCreated:
    if not idempotency_key:
        raise Problem(400, "Idempotency-Key header required")
    if not create_limit.allow(f"create:{request.client.host if request.client else 'x'}"):
        raise Problem(429, "Too many requests", "Please wait a minute and try again.")
    existing = db.scalar(select(Case).where(Case.idempotency_key == idempotency_key))
    if existing:
        response.status_code = 200
        return CaseCreated(id=existing.id, status=existing.status, access_token=case_token(existing.id))
    if not body.text and not body.blob_name:
        raise Problem(422, "Nothing to process", "Paste the letter text or upload a file.")
    if body.text and len(body.text) > MAX_PASTE_CHARS:
        raise Problem(413, "Text too long", "Pasted text can be at most 20,000 characters.")
    if body.text is not None and len(body.text.strip()) < 40:
        raise Problem(422, "Text too short", "Paste the full text of your denial letter.")
    dk, wrapped = new_data_key()
    case = Case(status=Status.RECEIVED.value, idempotency_key=idempotency_key)
    db.add(case)
    db.flush()
    if body.text:
        doc = Document(case_id=case.id, kind="pasted", sha256=hashlib.sha256(body.text.encode()).hexdigest(), text_encrypted=encrypt(dk, body.text, "document"), pages=1)
    else:
        try:
            data = get_blob_store().get(body.blob_name)
        except Exception:
            raise Problem(422, "Upload not found", "The file upload did not finish. Please try again.")
        doc = Document(case_id=case.id, kind=body.blob_name.rsplit(".", 1)[-1], blob_uri=f"uploads/{body.blob_name}", sha256=hashlib.sha256(data).hexdigest())
    db.add(doc)
    db.add(TokenVault(case_id=case.id, wrapped_data_key=wrapped, encrypted_map=encrypt(dk, "{}", "tokenmap")))
    get_queue().enqueue(db, "case.ingest", {"case_id": case.id}, case_id=case.id)  # transactional outbox
    db.add(AuditEvent(actor="user", action="case.create", entity=f"case:{case.id}"))
    db.commit()
    return CaseCreated(id=case.id, status=case.status, access_token=case_token(case.id))


# ---------------------------------------------------------------- read
@router.get("/cases/{case_id}")
def get_case(response: Response, case_id: str = Depends(require_case_access), db: Session = Depends(get_db)) -> dict[str, Any]:
    c = _case(db, case_id)
    response.headers["ETag"] = f'"{c.version}"'
    out: dict[str, Any] = {
        "id": c.id,
        "status": c.status,
        "version": c.version,
        "plan_type": c.plan_type,
        "state": c.state,
        "category": c.category,
        "degraded": c.degraded,
        "error": c.error,
        "created_at": c.created_at,
    }
    ex = db.scalar(select(Extraction).where(Extraction.case_id == case_id))
    if ex:
        _, tmap = _vault(db, case_id)
        fields = {}
        merged = {**ex.fields, **{k: v for k, v in (ex.user_corrections or {}).items() if v not in (None, "")}}
        for k, v in merged.items():
            val = rehydrate(v, tmap) if isinstance(v, str) else v
            if k == "member_id":
                val = mask(val)
            conf = (ex.field_confidence or {}).get(k, {})
            fields[k] = {"value": val, "confidence": conf.get("confidence", 1.0 if k in (ex.user_corrections or {}) else 0.0), "hint": conf.get("hint"), "corrected": k in (ex.user_corrections or {})}
        out["extraction"] = {"fields": fields, "injection_flags": (ex.injection or {}).get("flags", [])}
    cls = _latest(db, case_id, "classifier")
    if cls:
        pb = playbooks().get(c.category or cls["category"], {})
        out["classification"] = {
            **cls,
            "label": pb.get("label"),
            "why": pb.get("why"),
            "usually_means": pb.get("usually_means"),
            "confidence_words": confidence_words(cls["probability"]),
            "choices": [{"category": k, "label": playbooks()[k]["label"], "why": playbooks()[k]["why"]} for k in CATEGORIES],
        }
    res = _latest(db, case_id, "research")
    if res:
        today = date.today()
        dls = []
        for d in res["deadlines"]:
            due = date.fromisoformat(d["due_date"])
            dls.append({**d, "days_remaining": (due - today).days})
        out["deadlines"] = dls
        out["next_levels"] = res["next_levels"]
        out["evidence"] = res["evidence"]
        out["rules"] = [{k: r[k] for k in ("cite_id", "chunk_id", "citation_path", "source_kind", "status")} for r in res["rules"]]
        codes = (ex.fields.get("denial_codes") if ex else None) or []
        out["denial_code_notes"] = {cd: denial_code_descriptions().get(cd) for cd in codes}
        dl = dls[0]["due_date"] if dls else "[ADD: your appeal deadline]"
        pbk = playbooks()[c.category or cls["category"]] if cls else None
        if pbk:
            svc = (ex.fields.get("service") if ex else None) or "the service"
            out["clinician_request"] = pbk["clinician_request"].format(clinician="[ADD: clinician name]", service=svc, category_label=pbk["label"], deadline=dl)
    letter = _letter(db, case_id)
    if letter:
        out["letter"] = {"version": letter.version, "placeholders_remaining": letter.placeholders_remaining, "review_score": letter.review_score}
    return out


def confidence_words(p: float) -> str:
    if p >= 0.9:
        return "We are fairly sure about this."
    if p >= 0.7:
        return "This is our best guess, but please check it."
    return "We are not sure. Please pick the reason that best matches your letter."


# ---------------------------------------------------------------- SSE
TERMINAL = {"READY", "FAILED", "NEEDS_HUMAN", "AWAITING_CONFIRMATION", "NEEDS_CATEGORY"}


@router.get("/cases/{case_id}/events")
async def events(request: Request, case_id: str = Depends(require_case_access), last_event_id: str | None = Header(default=None)):
    bus = get_progress_bus()
    after = int(last_event_id) if last_event_id and last_event_id.isdigit() else int(request.query_params.get("after", 0))

    async def gen():
        yield ": connected\n\n"
        async for ev in bus.subscribe(case_id, after_id=after, heartbeat=10.0):
            if await request.is_disconnected():
                return
            if ev.get("type") == "heartbeat":
                yield ": heartbeat\n\n"
                continue
            yield f"id: {ev['id']}\nevent: {ev.get('type', 'message')}\ndata: {json.dumps(ev, default=str)}\n\n"
            terminal = (ev.get("type") == "status" and ev.get("status") in TERMINAL) or ev.get("type") == "needs_category"
            # during replay, a terminal event followed by later events is stale: keep streaming
            if terminal and not bus.history(case_id, ev["id"]):
                return

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- confirm
ID_FIELDS = {"member_id": "MEMBER_ID", "claim_number": "CLAIM_NUMBER"}
EDITABLE = {"insurer", "plan_type", "state", "claim_number", "member_id", "service", "date_of_service", "notice_date", "denial_reason", "denial_codes"}


@router.put("/cases/{case_id}/extraction")
def confirm_extraction(body: Corrections, case_id: str = Depends(require_case_access), if_match: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict:
    c = _case(db, case_id)
    if if_match is None:
        raise Problem(428, "If-Match header required", "Send the ETag you received from GET /v1/cases/{id}.")
    expected = int(if_match.strip('"W/ '))
    if c.status != Status.AWAITING_CONFIRMATION:
        raise Problem(409, "Not awaiting confirmation", f"Case is {c.status}.")
    ex = db.scalar(select(Extraction).where(Extraction.case_id == case_id))
    dk, tmap = _vault(db, case_id)
    corr = dict(ex.user_corrections or {})
    for k, v in body.fields.items():
        if k not in EDITABLE:
            raise Problem(422, "Unknown field", k)
        if k == "member_id" and isinstance(v, str) and "•" in v:
            continue  # masked value echoed back unchanged
        if k in ID_FIELDS and isinstance(v, str) and v.strip():
            v = tmap.token_for(ID_FIELDS[k], v.strip())  # identifiers are tokenized before storage
        if k == "denial_codes" and isinstance(v, str):
            v = [x.strip().upper() for x in re.split(r"[,\s]+", v) if x.strip()]
        if k == "plan_type" and v not in (None, "") and v not in {"employer_self_funded", "employer_fully_insured", "individual_marketplace", "medicare_advantage", "medicaid_managed_care"}:
            raise Problem(422, "Unknown plan type", str(v))
        current = ex.fields.get(k)
        if v != current:
            corr[k] = v
    ex.user_corrections = corr
    ex.confirmed = True
    if "plan_type" in corr:
        c.plan_type = corr["plan_type"]
    if "state" in corr:
        c.state = corr["state"]
    v = db.get(TokenVault, case_id)
    v.encrypted_map = encrypt(dk, tmap.to_json(), "tokenmap")
    try:
        transition(db, c, Status.CLASSIFYING, actor="user", expected_version=expected)
    except ConcurrencyConflict:
        db.rollback()
        raise Problem(412, "Case changed", "This case was updated elsewhere. Reload and try again.")
    if corr:
        db.add(AuditEvent(actor="user", action="extraction.corrected(labeled_example)", entity=f"case:{case_id}"))
    get_queue().enqueue(db, "case.draft", {"case_id": case_id}, case_id=case_id)
    db.commit()
    get_progress_bus().publish(case_id, {"type": "status", "status": Status.CLASSIFYING.value})
    return {"status": c.status, "version": c.version}


@router.post("/cases/{case_id}/category")
def choose_category(body: CategoryChoice, case_id: str = Depends(require_case_access), db: Session = Depends(get_db)) -> dict:
    c = _case(db, case_id)
    if body.category not in CATEGORIES:
        raise Problem(422, "Unknown category", body.category)
    if c.status != Status.NEEDS_CATEGORY:
        raise Problem(409, "Category not needed", f"Case is {c.status}.")
    c.category = body.category
    transition(db, c, Status.RESEARCHING, actor="user")
    get_queue().enqueue(db, "case.draft", {"case_id": case_id}, case_id=case_id)
    db.commit()
    get_progress_bus().publish(case_id, {"type": "status", "status": Status.RESEARCHING.value})
    return {"status": c.status}


# ---------------------------------------------------------------- letter
def _letter_view(db: Session, case_id: str, letter: Letter) -> dict:
    _, tmap = _vault(db, case_id)
    res = _latest(db, case_id, "research") or {"rules": [], "precedents": []}
    sources = {}
    for r in res["rules"]:
        sources[r["cite_id"]] = {"kind": "R", "chunk_id": r["chunk_id"], "citation": r["citation_path"], "excerpt": r["text"][:600], "status": r.get("status")}
    for p in res["precedents"]:
        sources[p["cite_id"]] = {
            "kind": "P",
            "chunk_id": p["chunk_id"],
            "citation": f"DMHC IMR {p['reference_id']} ({p['year']}, {'overturned' if p['overturned'] else 'upheld'})",
            "excerpt": p["excerpt"][:600],
        }
    sections = []
    for sec in letter.sentences:
        sections.append({**sec, "sentences": [{**s, "text": rehydrate(s["text"], tmap)} for s in sec["sentences"]]})
    rv = letter.review or {}
    return {
        "version": letter.version,
        "sections": sections,
        "sources": sources,
        "placeholders_remaining": letter.placeholders_remaining,
        "review": {"score": rv.get("score"), "warnings": rv.get("warnings", []), "blocking_issues": rv.get("blocking_issues", [])},
    }


@router.get("/cases/{case_id}/letter")
def get_letter(case_id: str = Depends(require_case_access), db: Session = Depends(get_db)) -> dict:
    letter = _letter(db, case_id)
    if letter is None:
        raise Problem(404, "Letter not ready")
    return _letter_view(db, case_id, letter)


PLACEHOLDER = re.compile(r"\[ADD: [^\]]+\]")


def _save_version(db: Session, case_id: str, sections: list[dict], review: dict, dk: bytes, tmap: TokenMap) -> Letter:
    from appeal_core.privacy.vault import tokenize

    stored = []
    body_parts = []
    count = 0
    for sec in sections:
        sents = []
        for s in sec["sentences"]:
            raw = s["text"]
            tok, _ = tokenize(raw, [], tmap)  # re-tokenize known identifiers before storing sentence JSON
            sents.append({**s, "text": tok})
            count += len(PLACEHOLDER.findall(raw))
        stored.append({**sec, "sentences": sents})
        joiner = "\n" if sec.get("id") in ("header", "closing") else " "
        body_parts.append(joiner.join(rehydrate(x["text"], tmap) + "".join(f" [{c}]" for c in x.get("citations", [])) for x in sents))
    prev = _letter(db, case_id)
    letter = Letter(case_id=case_id, version=(prev.version + 1 if prev else 1), body_encrypted=encrypt(dk, "\n\n".join(body_parts), "letter"), sentences=stored, placeholders_remaining=count, review_score=review.get("score", 0.0), review=review)
    db.add(letter)
    return letter


@router.put("/cases/{case_id}/letter")
def put_letter(body: LetterEdit, case_id: str = Depends(require_case_access), db: Session = Depends(get_db)) -> dict:
    prev = _letter(db, case_id)
    if prev is None:
        raise Problem(404, "Letter not ready")
    dk, tmap = _vault(db, case_id)
    letter = _save_version(db, case_id, body.sections, prev.review or {}, dk, tmap)
    db.add(AuditEvent(actor="user", action="letter.edit", entity=f"case:{case_id}"))
    db.commit()
    return _letter_view(db, case_id, letter)


@router.post("/cases/{case_id}/letter/regenerate")
def regenerate(body: RegenerateRequest, request: Request, case_id: str = Depends(require_case_access), db: Session = Depends(get_db)) -> dict:
    if not regen_limit.allow(f"regen:{case_id}") or not regen_limit.allow(f"regen-ip:{request.client.host if request.client else 'x'}"):
        raise Problem(429, "Too many regenerations", "Please wait a minute before regenerating again.")
    c = _case(db, case_id)
    prev = _letter(db, case_id)
    res = _latest(db, case_id, "research")
    if prev is None or res is None:
        raise Problem(404, "Letter not ready")
    from appeal_worker import agents
    from appeal_worker.orchestrator import Orchestrator

    orch = Orchestrator.__new__(Orchestrator)
    orch.Session = None
    facts, tmap, dk, flags = Orchestrator.facts_for(orch, db, case_id)
    research = Research(**res)
    draft = agents.write(facts, c.category, research, tmap.raw_values(), revision=99, style=body.reason, section_id=body.section_id)
    rv = agents.review(draft, research, facts, set(tmap.tokens), flags)
    # Only the requested section changes; the reviewer re-runs on the result.
    new_sec = next((s for s in draft.model_dump()["sections"] if s["id"] == body.section_id), None)
    if new_sec is None:
        raise Problem(422, "Unknown section", body.section_id)
    sections = []
    for sec in prev.sentences:
        sections.append(new_sec if sec["id"] == body.section_id else sec)
    sections = [{**s, "sentences": [{**x, "text": rehydrate(x["text"], tmap)} for x in s["sentences"]]} for s in sections]
    letter = _save_version(db, case_id, sections, rv.model_dump(), dk, tmap)
    db.add(AuditEvent(actor="user", action=f"letter.regenerate:{body.reason}", entity=f"case:{case_id}"))
    db.commit()
    return _letter_view(db, case_id, letter)


# ---------------------------------------------------------------- precedents
@router.get("/cases/{case_id}/precedents")
def precedents(case_id: str = Depends(require_case_access), db: Session = Depends(get_db)) -> dict:
    res = _latest(db, case_id, "research")
    if res is None:
        raise Problem(404, "Research not ready")
    return {
        "stats": res.get("stats"),
        "precedents": res["precedents"],
        "explainer": "These are California decisions. Your plan, state and facts may differ. A low overturn rate does not mean you shouldn't appeal.",
        "attribution": "Source: California Department of Managed Health Care, Independent Medical Review determinations (CC BY).",
    }


# ---------------------------------------------------------------- exports
@router.get("/cases/{case_id}/exports/{fmt}")
def export(fmt: str, case_id: str = Depends(require_case_access), db: Session = Depends(get_db)) -> Response:
    from appeal_api.exports import render_docx, render_ics, render_pdf

    if fmt == "ics":
        res = _latest(db, case_id, "research")
        if not res or not res["deadlines"]:
            raise Problem(404, "No cited deadline", "We only show deadlines that come from a cited rule.")
        return Response(render_ics(res["deadlines"][0], case_id), media_type="text/calendar", headers={"Content-Disposition": 'attachment; filename="appeal-deadline.ics"'})
    letter = _letter(db, case_id)
    if letter is None:
        raise Problem(404, "Letter not ready")
    if letter.placeholders_remaining > 0:
        raise Problem(409, "Fill in the placeholders first", f"{letter.placeholders_remaining} placeholder(s) like [ADD: ...] still need your information.")
    view = _letter_view(db, case_id, letter)
    if fmt == "pdf":
        return Response(render_pdf(view), media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="appeal-letter.pdf"'})
    if fmt == "docx":
        return Response(render_docx(view), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers={"Content-Disposition": 'attachment; filename="appeal-letter.docx"'})
    raise Problem(404, "Unknown export format")


# ---------------------------------------------------------------- delete
@router.delete("/cases/{case_id}", status_code=204)
def delete_case(case_id: str = Depends(require_case_access), db: Session = Depends(get_db)) -> Response:
    c = _case(db, case_id)
    for doc in db.scalars(select(Document).where(Document.case_id == case_id)):
        if doc.blob_uri:
            get_blob_store().delete(doc.blob_uri.split("/", 1)[1])
    db.delete(c)  # cascades to document, extraction, agent_run, letter, citation, deadline, token_vault
    db.add(AuditEvent(actor="user", action="case.delete", entity=f"case:{case_id}"))
    db.commit()
    try:
        get_progress_bus().delete(case_id)
    except Exception:
        pass
    return Response(status_code=204)


# ---------------------------------------------------------------- public KB
@router.get("/kb/chunks/{chunk_id:path}")
def kb_chunk(chunk_id: str, db: Session = Depends(get_db)) -> dict:
    k = db.get(KbChunk, chunk_id)
    if k:
        return {
            "id": k.id,
            "kind": k.source_kind,
            "citation": k.citation_path,
            "heading": k.heading,
            "text": k.text,
            "url": k.url,
            "effective_date": k.effective_date,
            "status": k.status,
            "draft_content": k.status == "needs_human_review",
        }
    p = db.get(PrecedentChunk, chunk_id)
    if p:
        return {
            "id": p.id,
            "kind": "precedent",
            "citation": f"DMHC IMR {p.reference_id}",
            "heading": f"{p.year} · {p.treatment_category} / {p.treatment_subcategory} · {'Overturned' if p.overturned else 'Upheld'}",
            "text": p.text,
            "attribution": "California Department of Managed Health Care, Independent Medical Review determinations (CC BY)",
        }
    raise Problem(404, "Source not found")


@router.get("/insights/insurers")
def insurers(db: Session = Depends(get_db)) -> dict:
    from appeal_core.settings import get_settings

    if not get_settings().feature_insurer_insights:
        raise Problem(404, "Insurer insights are not enabled", "FEATURE_INSURER_INSIGHTS=false (D3 data not loaded).")
    from appeal_core.models import InsurerStats

    rows = db.scalars(select(InsurerStats).order_by(InsurerStats.state, InsurerStats.issuer)).all()
    return {
        "disclaimer": "CMS notes that denial counts are not necessarily indicative of an issuer's strength or plan quality.",
        "issuers": [
            {
                "plan_year": r.plan_year,
                "state": r.state,
                "issuer": r.issuer,
                "claims_received": r.claims_received,
                "claims_denied": r.claims_denied,
                "denial_rate": (r.claims_denied / r.claims_received) if r.claims_received else None,
                "appeals_filed": r.appeals_filed,
                "appeals_overturned": r.appeals_overturned,
            }
            for r in rows
        ],
    }
