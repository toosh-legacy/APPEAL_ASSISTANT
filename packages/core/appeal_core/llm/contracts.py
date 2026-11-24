"""Structured-output contracts for each LLM step (`ChatOpenAI.with_structured_output(<model>)`).

They are kept small and flat so OpenAI's JSON-schema mode can enforce them. Agent outputs (schemas.py) are
built from these after deterministic checks, never taken from the model unchecked.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from appeal_core.schemas import Category


class ExtractionOut(BaseModel):
    """Intake: facts copied from the TOKENIZED letter. null when the letter does not say."""

    insurer: str | None = Field(description="insurance company name as written")
    plan_type: (
        Literal[
            "employer_self_funded",
            "employer_fully_insured",
            "individual_marketplace",
            "medicare_advantage",
            "medicaid_managed_care",
        ]
        | None
    ) = Field(description="plan type if the letter states or clearly implies it")
    state: str | None = Field(description="two-letter US state code")
    claim_number: str | None = Field(description="claim/reference number token, e.g. [CLAIM_NUMBER_1]")
    member_id: str | None = Field(description="member ID token, e.g. [MEMBER_ID_1]")
    service: str | None = Field(description="the treatment, test or item that was denied, as written")
    date_of_service: str | None = Field(description="YYYY-MM-DD")
    notice_date: str | None = Field(description="date of the letter, YYYY-MM-DD")
    denial_reason: str | None = Field(
        description="the sentence giving the reason for the denial, copied exactly"
    )
    denial_codes: list[str] = Field(description='denial or remark codes such as "CO-50"; empty if none')


class CategoryOut(BaseModel):
    """Classifier fallback, used only when the calibrated M1 model is unsure."""

    category: Category
    confidence: float = Field(ge=0, le=1, description="probability the category is right")
    rationale: str = Field(description="one sentence, quoting the words that decided it")


class QueryRewrites(BaseModel):
    queries: list[str] = Field(
        description="2-3 short search queries: legal-concept, plain-language, service-specific"
    )


class SentenceOut(BaseModel):
    text: str
    citations: list[str] = Field(description="R/P IDs this sentence relies on; empty for non-legal sentences")
    kind: Literal["fact", "legal", "precedent", "request", "closing", "header"]
    argument_id: str | None = Field(description="slug for legal/fact/precedent sentences, else null")


class SectionOut(BaseModel):
    id: Literal["header", "intro", "grounds", "facts", "precedents", "request", "closing"]
    title: str
    sentences: list[SentenceOut]


class DraftOut(BaseModel):
    """Writer: the letter as sections of sentences, each carrying the R/P IDs it relies on. Every field is
    required (OpenAI strict JSON schema); defaults are filled in when it becomes a LetterDraft."""

    sections: list[SectionOut]


ReviewCode = Literal["unsupported_claim", "wrong_fact", "tone", "unclear"]


class ReviewIssue(BaseModel):
    section_id: str
    sentence_index: int
    code: ReviewCode
    message: str
    fact_field: str | None = Field(description="for wrong_fact: the facts key the sentence contradicts, else null")
    fact_value: str | None = Field(description="for wrong_fact: that key's value copied exactly from facts, else null")


class ReviewOut(BaseModel):
    """Reviewer (LLM judge) on top of the deterministic checks. unsupported_claim / wrong_fact block."""

    issues: list[ReviewIssue]


BLOCKING_REVIEW_CODES = {"unsupported_claim", "wrong_fact"}
