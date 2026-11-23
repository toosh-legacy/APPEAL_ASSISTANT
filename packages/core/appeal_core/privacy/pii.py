"""PII detection: regex recognizers + optional Presidio Analyzer (PIIDetector interface).

Regex recognizers cover the identifier shapes that matter for denial letters (member IDs, claim
numbers, phones, emails, SSNs, dates of birth, addresses, labelled names). Presidio adds NER for
person names in free text. If Presidio or its spaCy model is unavailable, regex-only mode is used.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol


@dataclass(frozen=True)
class PIISpan:
    start: int
    end: int
    entity: str
    text: str
    score: float
    source: str  # regex | presidio


class PIIDetector(Protocol):
    def detect(self, text: str) -> list[PIISpan]: ...


_LABEL = r"(?:[ \t]*[:#][ \t]*|[ \t]+)"
# Ordered: more specific first. Each pattern's group(1) (if present) is the identifier; else whole match.
REGEX_RECOGNIZERS: list[tuple[str, re.Pattern[str], float]] = [
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), 0.95),
    ("US_SSN", re.compile(r"\b(?!000|666)\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b"), 0.9),
    (
        "PHONE",
        re.compile(r"(?<![\w-])(?:\+?1[\s.-]?)?(?:\(\d{3}\)\s?|\d{3}[\s.-])\d{3}[\s.-]\d{4}(?![\w-])"),
        0.85,
    ),
    (
        "MEMBER_ID",
        re.compile(
            r"(?i)(?:member|subscriber|enrollee|patient|policy|insured)\s*(?:id|identification|number|no\.?|#)"
            + _LABEL
            + r"([A-Z0-9][A-Z0-9 \-]{4,22}[A-Z0-9])"
        ),
        0.9,
    ),
    ("MEMBER_ID", re.compile(r"\b(ZZTEST[\s-]?[A-Z0-9][A-Z0-9\s-]{2,14}[A-Z0-9])\b"), 0.95),
    (
        "CLAIM_NUMBER",
        re.compile(
            r"(?i)(?:claim|reference|case|authorization|auth|ref)\s*(?:number|no\.?|#|id)" + _LABEL + r"([A-Z0-9][A-Z0-9\-]{4,24})"
        ),
        0.85,
    ),
    (
        "MRN",
        re.compile(r"(?i)(?:MRN|medical record(?: number)?)" + _LABEL + r"([A-Z0-9\-]{4,20})"),
        0.85,
    ),
    (
        "DOB",
        re.compile(
            r"(?i)(?:DOB|date of birth|birth ?date)" + _LABEL + r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|[A-Z][a-z]+ \d{1,2}, \d{4})"
        ),
        0.9,
    ),
    (
        "ADDRESS",
        re.compile(
            r"\b(\d{1,6}\s+(?:[A-Z][a-z]+\s){1,3}(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Lane|Ln|Dr|Drive|Way|Ct|Court)\.?"
            r"(?:,?\s+(?:Apt|Suite|Unit)\s*\w+)?)"
        ),
        0.8,
    ),
    (
        "PERSON",
        re.compile(
            r"(?:(?i:dear|patient|member|name|enrollee|subscriber|insured|attn|to)[ \t]*:?[ \t]+)"
            r"((?:Mr\.|Ms\.|Mrs\.|Dr\.)?\s?[A-Z][a-z]+(?:[ \t][A-Z]\.?)?[ \t][A-Z][a-z]+(?:-[A-Z][a-z]+)?)"
        ),
        0.75,
    ),
    ("ZIP", re.compile(r"(?<=[A-Z]{2} )\d{5}(?:-\d{4})?\b"), 0.6),
]

# Words that look like names after "Dear"/"Member" labels but are not identifiers.
_NOT_NAMES = {
    "Health Plan",
    "Member Services",
    "Customer Service",
    "Medical Director",
    "Claims Department",
    "Appeals Department",
    "Sir Madam",
}


def regex_detect(text: str) -> list[PIISpan]:
    spans: list[PIISpan] = []
    for entity, pat, score in REGEX_RECOGNIZERS:
        for m in pat.finditer(text):
            if m.lastindex:
                s, e = m.start(1), m.end(1)
            else:
                s, e = m.start(), m.end()
            val = text[s:e].strip()
            # trim trailing whitespace inside span
            e = s + len(text[s:e].rstrip())
            if not val:
                continue
            if entity == "PERSON" and val in _NOT_NAMES:
                continue
            spans.append(PIISpan(s, e, entity, text[s:e], score, "regex"))
    return spans


@lru_cache
def _presidio():
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider

        provider = NlpEngineProvider(
            nlp_configuration={"nlp_engine_name": "spacy", "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}]}
        )
        return AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["en"])
    except Exception:  # model or package missing -> regex only
        return None


def presidio_available() -> bool:
    return _presidio() is not None


def merge_spans(spans: list[PIISpan]) -> list[PIISpan]:
    """Resolve overlaps: keep the longest (then highest score) span."""
    spans = sorted(spans, key=lambda s: (s.start, -(s.end - s.start), -s.score))
    out: list[PIISpan] = []
    for sp in spans:
        if out and sp.start < out[-1].end:
            prev = out[-1]
            if (sp.end - sp.start) > (prev.end - prev.start):
                out[-1] = sp
            continue
        out.append(sp)
    return out


class LocalPIIDetector:
    """Regex + Presidio (when installed)."""

    PRESIDIO_ENTITIES = ["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "US_SSN"]

    def __init__(self, use_presidio: bool = True, presidio_threshold: float = 0.7):
        self.use_presidio = use_presidio
        self.presidio_threshold = presidio_threshold

    def detect(self, text: str) -> list[PIISpan]:
        spans = regex_detect(text)
        engine = _presidio() if self.use_presidio else None
        if engine is not None:
            for r in engine.analyze(text=text, language="en", entities=self.PRESIDIO_ENTITIES):
                if r.score < self.presidio_threshold:
                    continue
                val = text[r.start : r.end]
                if r.entity_type == "PERSON" and (len(val.split()) < 2 or val in _NOT_NAMES or not val[0].isupper()):
                    continue
                ent = {"PHONE_NUMBER": "PHONE", "EMAIL_ADDRESS": "EMAIL"}.get(r.entity_type, r.entity_type)
                spans.append(PIISpan(r.start, r.end, ent, val, float(r.score), "presidio"))
        return merge_spans(spans)


def get_pii_detector(backend: str = "local") -> PIIDetector:
    if backend == "local":
        return LocalPIIDetector()
    if backend == "azure":
        from appeal_core.adapters.azure import AzureLanguagePIIDetector

        return AzureLanguagePIIDetector()
    raise ValueError(f"unknown PII backend {backend}")
