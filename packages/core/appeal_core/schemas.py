"""Agent I/O contracts (SPEC 8.1). Exported as JSON Schema to packages/schemas/."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Category = Literal[
    "medical_necessity",
    "prior_authorization",
    "out_of_network",
    "coding_billing_error",
    "experimental_investigational",
    "not_covered_benefit",
    "timely_filing",
    "other_unclear",
]
PlanType = Literal[
    "employer_self_funded",
    "employer_fully_insured",
    "individual_marketplace",
    "medicare_advantage",
    "medicaid_managed_care",
]

EXTRACTED_FIELDS = [
    "insurer",
    "plan_type",
    "state",
    "claim_number",
    "member_id",
    "service",
    "date_of_service",
    "notice_date",
    "denial_reason",
    "denial_codes",
]


class FieldValue(BaseModel):
    value: str | list[str] | None = None
    confidence: float = Field(0.0, ge=0, le=1)
    hint: str | None = None  # "where to find this on your letter"


class ExtractedDenial(BaseModel):
    """Intake output. Values are TOKENIZED: identifiers appear as vault tokens like [MEMBER_ID_1]."""

    fields: dict[str, FieldValue]
    missing_fields: list[str] = []
    plan_type: PlanType | None = None
    state: str | None = None
    injection_flags: list[str] = []


class Classification(BaseModel):
    category: Category
    probability: float = Field(ge=0, le=1)
    alternatives: list[tuple[Category, float]] = []
    rationale: str
    source: Literal["denial_code", "model", "rules", "user", "llm"]
    needs_user: bool = False
    flagged_for_review: bool = False


class RuleCite(BaseModel):
    cite_id: str  # R1..Rn
    chunk_id: str
    citation_path: str
    heading: str | None = None
    text: str
    source_kind: Literal["regulation", "summary"]
    score: float = 0.0
    status: str | None = None


class PrecedentCite(BaseModel):
    cite_id: str  # P1..Pn
    chunk_id: str
    reference_id: str
    year: int
    treatment: str | None = None
    treatment_subcategory: str | None = None
    diagnosis: str | None = None
    type: str | None = None
    overturned: bool
    excerpt: str
    score: float = 0.0


class Stats(BaseModel):
    scope: str  # e.g. "Diag Imag & Screen / MRI"
    n: int
    overturned_n: int
    rate: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    by_year: list[dict] = []
    enough_data: bool = False
    model_estimate: float | None = None
    model_used: bool = False
    note: str = "These are California decisions. Your plan, state and facts may differ. A low overturn rate does not mean you shouldn't appeal."


class Deadline(BaseModel):
    kind: str
    label: str
    rule_id: str
    days: int
    trigger_date: str
    due_date: str
    basis_chunk_id: str
    basis_citation: str | None = None
    letter_text: str | None = None
    cite_id: str | None = None


class NextLevel(BaseModel):
    kind: str
    label: str
    window_text: str
    rule_id: str
    basis_chunk_id: str
    cite_id: str | None = None


class Research(BaseModel):
    rules: list[RuleCite]
    precedents: list[PrecedentCite]
    stats: Stats | None = None
    deadlines: list[Deadline] = []
    next_levels: list[NextLevel] = []
    arguments: list[str] = []
    evidence: list[str] = []
    imr_type_prediction: str | None = None


class Sentence(BaseModel):
    text: str  # tokenized; may contain [ADD: ...] placeholders
    citations: list[str] = []  # R/P IDs
    kind: Literal["fact", "legal", "precedent", "request", "closing", "header"] = "fact"
    argument_id: str | None = None


class Section(BaseModel):
    id: str
    title: str
    sentences: list[Sentence]


class LetterDraft(BaseModel):
    sections: list[Section]
    placeholders: list[str] = []
    revision: int = 0
    degraded: bool = False


class Issue(BaseModel):
    code: str
    message: str
    section_id: str | None = None
    sentence_index: int | None = None
    blocking: bool = True


class SentenceVerdict(BaseModel):
    section_id: str
    sentence_index: int
    supported: bool
    reason: str
    score: float = 0.0


class Review(BaseModel):
    blocking_issues: list[Issue] = []
    warnings: list[Issue] = []
    verdicts: list[SentenceVerdict] = []
    score: float = 0.0


def export_json_schemas(out_dir) -> list[str]:
    import json
    from pathlib import Path

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    models: list[type[BaseModel]] = [ExtractedDenial, Classification, Research, LetterDraft, Review]
    for m in models:
        p = out / f"{m.__name__}.schema.json"
        p.write_text(json.dumps(m.model_json_schema(), indent=2), encoding="utf-8")
        written.append(p.name)
    return written
