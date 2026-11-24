"""The five agents (SPEC 8.1). Each is a pure-ish function from validated input to a validated output model.
No agent has a tool that sends messages, reaches the internet or reads another case (hard rule 4)."""

from __future__ import annotations

import re
from collections import Counter
from datetime import date
from typing import Any, TypedDict

from appeal_core.adapters import get_injection_detector, get_llm
from appeal_core.deadlines import compute_deadlines, next_level_options
from appeal_core.kb import CATEGORIES, playbooks
from appeal_core.llm.base import ProviderUnavailable
from appeal_core.llm.contracts import BLOCKING_REVIEW_CODES
from appeal_core.llm.offline import classify_by_codes, offline_write
from appeal_core.privacy.injection import spans_to_neutralize
from appeal_core.privacy.pii import get_pii_detector
from appeal_core.privacy.vault import TokenMap, tokenize
from appeal_core.retrieval.lc_retriever import PrecedentRetriever, RulesRetriever
from appeal_core.retrieval.lc_retriever import rows as lc_rows
from appeal_core.schemas import (
    Classification,
    Deadline,
    ExtractedDenial,
    Issue,
    LetterDraft,
    NextLevel,
    PrecedentCite,
    Research,
    Review,
    RuleCite,
    SentenceVerdict,
    Stats,
)
from appeal_core.settings import get_settings
from appeal_core.text_support import check_support


# ====================================================================== Intake
def intake(raw_text: str, tmap: TokenMap | None = None) -> tuple[ExtractedDenial, str, TokenMap]:
    """PII detect -> tokenize -> injection check -> structured extraction (on tokenized text only)."""
    spans = get_pii_detector(get_settings().pii_backend).detect(raw_text)
    tokenized, tmap = tokenize(raw_text, spans, tmap)
    flags = get_injection_detector().detect(tokenized)
    out = get_llm().extract(tokenized, tmap.raw_values())
    # untrusted text must not flow into the reason field verbatim if it contains injection
    reason = out["fields"].get("denial_reason", {}).get("value")
    if reason and flags:
        for s, e in sorted(spans_to_neutralize(reason), reverse=True):
            reason = reason[:s] + reason[e:]
        out["fields"]["denial_reason"]["value"] = reason.strip() or None
    ext = ExtractedDenial(**out, injection_flags=flags)
    return ext, tokenized, tmap


# ====================================================================== Classifier
KEYWORDS = {
    "medical_necessity": r"medically necessary|medical necessity|medically (appropriate|required)|level of care|clinical (criteria|records)|less intensive",
    "prior_authorization": r"prior auth|authoriz|precertif|pre-service approval|advance approval|pre-approval",
    "out_of_network": r"out[- ]of[- ]network|non-?participating|not in (your|the) (plan's )?network|outside the plan network|in-network",
    "coding_billing_error": r"code|coding|billing|modifier|duplicate|resubmit|missing or invalid|lacks required information",
    "experimental_investigational": r"experimental|investigational|unproven|clinical study|clinical trial|effectiveness",
    "not_covered_benefit": r"not a covered benefit|excludes?|exclusion|not covered under|outside the benefits|non-?covered",
    "timely_filing": r"timely filing|filing deadline|untimely|time limit|too late|submission (window|period)|after the filing",
}


def rule_scores(reason: str) -> dict[str, float]:
    sc = {c: float(len(re.findall(p, reason, re.I))) + 0.05 for c, p in KEYWORDS.items()}
    sc["other_unclear"] = 0.3  # no keyword evidence -> low confidence -> ask the user
    tot = sum(sc.values())
    return {c: v / tot for c, v in sc.items()}


def classify(reason: str | None, codes: list[str], service: str | None, threshold: float | None = None, raw_values: list[str] | None = None) -> Classification:
    threshold = get_settings().classifier_threshold if threshold is None else threshold
    reason = reason or ""
    probs: dict[str, float] | None = None
    source = "rules"
    try:
        from appeal_ml.registry import get_registry

        m1 = get_registry().m1()
        if m1 is not None:
            probs = m1.predict_proba_one(reason, codes)
            source = "model"
            threshold = getattr(m1, "threshold", threshold)  # chosen from the coverage-vs-accuracy curve
    except Exception:
        probs = None
    if probs is None:
        probs = rule_scores(reason)
    ranked = sorted(probs.items(), key=lambda kv: -kv[1])
    top, p = ranked[0]
    flagged = False
    code_cat = classify_by_codes(codes)
    if code_cat:
        model_p_other = max((v for c, v in probs.items() if c != code_cat), default=0.0)
        if source == "model" and model_p_other > 0.9:
            flagged = True  # model strongly disagrees with the code map -> keep model answer, flag for review
        else:
            top, p, source = code_cat, max(0.95, probs.get(code_cat, 0.0)), "denial_code"
    rationale = {
        "denial_code": f"The denial code(s) {', '.join(codes)} map to this category.",
        "model": "Predicted from the wording of the denial reason by the denial-category model (M1).",
        "rules": "Matched keywords in the denial reason (fallback rules).",
    }[source]
    if p < threshold and source != "denial_code" and reason:
        # M1 is unsure: ask the cheap-tier LLM; accept it only when it is at least as confident as the threshold
        try:
            got = get_llm().classify(reason, codes, service, raw_values or [])
            if got.confidence >= threshold:
                top, p, source, rationale = got.category, got.confidence, "llm", got.rationale
        except ProviderUnavailable:
            pass
    needs_user = p < threshold
    alts = [(c, round(v, 4)) for c, v in ranked if c != top][:3]
    return Classification.model_validate(
        {"category": top, "probability": round(float(p), 4), "alternatives": alts, "rationale": rationale, "source": source, "needs_user": needs_user, "flagged_for_review": flagged}
    )


# ====================================================================== Research
def _service_categories(service: str | None, retriever) -> tuple[str | None, str | None, str | None]:
    if not service:
        return None, None, None
    hits = retriever.search_precedents([service], k=30, mode="keyword", diversify=False)
    if not hits:
        return None, None, None
    tc = Counter(h["treatment_category"] for h in hits).most_common(1)[0][0]
    tsc = Counter(h["treatment_subcategory"] for h in hits if h["treatment_category"] == tc).most_common(1)[0][0]
    dc = Counter(h["diagnosis_category"] for h in hits if h["treatment_category"] == tc).most_common(1)[0][0]
    return tc, tsc, dc


CATEGORY_QUERY = {
    "medical_necessity": "medical judgment health care professional appropriate training experience appeal",
    "prior_authorization": "prior authorization pre-service claim urgent care approval",
    "out_of_network": "emergency services out-of-network without prior authorization cost-sharing",
    "coding_billing_error": "claim information denial code reason notice",
    "experimental_investigational": "experimental investigational medical judgment health care professional",
    "not_covered_benefit": "specific plan provisions denial reason notice",
    "timely_filing": "claim filing reasonable procedures notice",
    "other_unclear": "specific reason adverse benefit determination notice",
}
IMR_TYPE_FOR = {"medical_necessity": "Medical Necessity", "experimental_investigational": "Experimental/Investigational"}


def research(category: str, plan_type: str | None, service: str | None, reason: str | None, notice_date: str | None, retriever) -> Research:
    llm = get_llm()
    deadlines = compute_deadlines(plan_type, date.fromisoformat(notice_date) if notice_date else None)
    levels = next_level_options(plan_type)
    required = [d["basis_chunk_id"] for d in deadlines] + [n["basis_chunk_id"] for n in levels[:1]]
    base = f"appeal {category.replace('_', ' ')} {CATEGORY_QUERY[category]}"
    queries = llm.rewrite_query(base, [])
    if reason:
        queries.append(reason[:200])
    rules_raw = lc_rows(RulesRetriever(hybrid=retriever, plan_type=plan_type, k=8, required_ids=required, extra_queries=queries[1:]).invoke(queries[0]))
    rules = [
        RuleCite(
            cite_id=f"R{i + 1}",
            chunk_id=r["id"],
            citation_path=r["citation_path"],
            heading=r.get("heading"),
            text=r["text"],
            source_kind=r["source_kind"],
            score=round(r.get("score", 0.0), 5),
            status=r.get("status"),
        )
        for i, r in enumerate(rules_raw)
    ]
    cite_for_chunk = {r.chunk_id: r.cite_id for r in rules}
    dls = []
    for d in deadlines:
        if d["basis_chunk_id"] in cite_for_chunk:
            dls.append({**d, "cite_id": cite_for_chunk[d["basis_chunk_id"]]})
    nls = [{**n, "cite_id": cite_for_chunk.get(n["basis_chunk_id"])} for n in levels]

    tc, tsc, dc = _service_categories(service, retriever)
    imr_type = IMR_TYPE_FOR.get(category)
    m2_pred = None
    try:
        from appeal_ml.registry import get_registry

        m2 = get_registry().m2()
        if m2 is not None and (reason or service):
            m2_pred = m2.predict_one(f"{service or ''}. {reason or ''}")
            if category not in IMR_TYPE_FOR:
                imr_type = None
    except Exception:
        m2_pred = None
    prec_queries = [q for q in [f"{service or ''} {reason or ''}".strip(), service] if q]
    precs_raw = (
        lc_rows(PrecedentRetriever(hybrid=retriever, treatment_category=tc, treatment_subcategory=tsc, imr_type=imr_type, k=5, extra_queries=prec_queries[1:]).invoke(prec_queries[0]))
        if prec_queries
        else []
    )
    precs = [
        PrecedentCite(
            cite_id=f"P{i + 1}",
            chunk_id=p["id"],
            reference_id=p["reference_id"],
            year=p["year"],
            treatment=p["treatment_category"],
            treatment_subcategory=p["treatment_subcategory"],
            diagnosis=p["diagnosis_category"],
            type=p["type"],
            overturned=p["overturned"],
            excerpt=p["text"],
            score=round(p.get("score", 0.0), 5),
        )
        for i, p in enumerate(precs_raw)
    ]
    from appeal_core.retrieval.imr_stats import get_stats

    st = get_stats(tc, tsc, dc) if tc else None
    stats = None
    if st:
        stats = Stats(**{k: v for k, v in st.items() if k in Stats.model_fields})
        try:
            from appeal_ml.registry import get_registry

            m3 = get_registry().m3()
            if m3 is not None and st["n"] >= 20:
                est, beats = m3.estimate(tc, tsc, dc, imr_type or "Medical Necessity")
                stats.model_estimate = est
                stats.model_used = bool(beats)
        except Exception:
            pass
    pb = playbooks()[category]
    return Research(
        rules=rules,
        precedents=precs,
        stats=stats,
        deadlines=[Deadline.model_validate(d) for d in dls],
        next_levels=[NextLevel.model_validate(n) for n in nls],
        arguments=[a["id"] for a in pb.get("legal", [])],
        evidence=pb.get("evidence", []),
        imr_type_prediction=m2_pred,
    )


# ====================================================================== Writer
def write(facts: dict[str, Any], category: str, res: Research, raw_values: list[str], revision: int = 0, drop: list[str] | None = None, style: str | None = None, section_id: str | None = None) -> LetterDraft:
    req = {
        "facts": facts,
        "category": category,
        "rules": [r.model_dump() for r in res.rules],
        "precedents": [p.model_dump() for p in res.precedents],
        "deadlines": [d.model_dump() for d in res.deadlines],
        "revision": revision,
        "drop_sentences": drop or [],
        "style": style,
        "section_id": section_id,
    }
    llm = get_llm()
    degraded = False
    try:
        out = llm.write(req, raw_values)
    except ProviderUnavailable:
        out = offline_write(req)  # degraded mode: deterministic playbook writer
        degraded = True
    d = LetterDraft(**out)
    d.degraded = degraded
    return d


# ====================================================================== Reviewer
BANNED = [
    (re.compile(r"\bguarantee", re.I), "guarantee_of_success"),
    (re.compile(r"\byou will win\b|\bwill (definitely|certainly) (be )?(approved|overturned)", re.I), "guarantee_of_success"),
    (re.compile(r"\bas an ai\b|\blanguage model\b", re.I), "as_an_ai"),
    (re.compile(r"\b(sue|lawsuit|legal action|attorney general|or else|consequences)\b", re.I), "threat"),
    (re.compile(r"\b(fraud|bad faith)\b", re.I), "unsupported_accusation"),
    (re.compile(r"\b(should not|shouldn't|don't|do not) (bother to )?appeal\b|\bnot worth appealing\b", re.I), "discourages_appeal"),
]
NON_BINDING_RE = re.compile(r"\bindependent reviewers? in similar\b.*\b(found|determined)\b", re.I)
TOKEN_RE = re.compile(r"\[([A-Z_]+)_(\d+)\]")


class _Loc(TypedDict):
    section_id: str
    sentence_index: int


def review(draft: LetterDraft, res: Research, facts: dict[str, Any], known_tokens: set[str], injection_flags: list[str] | None = None, raw_values: list[str] | None = None) -> Review:
    allowed = {r.cite_id: r for r in res.rules} | {p.cite_id: p for p in res.precedents}
    deadline_days = {str(d.days) for d in res.deadlines}
    blocking: list[Issue] = []
    warnings: list[Issue] = []
    verdicts: list[SentenceVerdict] = []
    for sec in draft.sections:
        for i, s in enumerate(sec.sentences):
            loc: _Loc = {"section_id": sec.id, "sentence_index": i}
            for pat, code in BANNED:
                if pat.search(s.text):
                    blocking.append(Issue(code=code, message=f"Remove wording: '{pat.pattern}'", **loc))
            for tok in TOKEN_RE.findall(s.text):
                t = f"[{tok[0]}_{tok[1]}]"
                if t not in known_tokens:
                    blocking.append(Issue(code="unknown_identifier", message=f"Identifier {t} is not one the member provided", **loc))
            bad = [c for c in s.citations if c not in allowed]
            if bad:
                blocking.append(Issue(code="invalid_citation", message=f"Cited IDs not in the retrieval set: {bad}", **loc))
                continue
            if s.kind == "legal" and not any(c.startswith("R") for c in s.citations):
                blocking.append(Issue(code="legal_without_rule", message="A legal claim must cite at least one R-ID", **loc))
                continue
            if s.kind == "precedent":
                if not any(c.startswith("P") for c in s.citations):
                    blocking.append(Issue(code="precedent_without_p", message="A sentence about similar cases must cite a P-ID", **loc))
                    continue
                if not NON_BINDING_RE.search(s.text):
                    blocking.append(Issue(code="binding_wording", message="Use non-binding wording for similar cases", **loc))
            if s.citations:
                passages = []
                for c in s.citations:
                    src = allowed[c]
                    passages.append(src.text if isinstance(src, RuleCite) else src.excerpt)
                    if isinstance(src, RuleCite) and src.heading:
                        passages.append(src.heading)
                ok, why, sc = check_support(s.text, passages, allowed_numbers=deadline_days if s.argument_id == "deadline" else None)
                if s.argument_id == "deadline":
                    nums = set(re.findall(r"\b(\d+)(?:-day| days| calendar days)\b", s.text))
                    if not nums or not nums <= deadline_days:
                        ok, why = False, "deadline number does not match the deadline calculator"
                verdicts.append(SentenceVerdict(**loc, supported=ok, reason=why, score=round(sc, 3)))
                if not ok:
                    blocking.append(Issue(code="unsupported", message=f"Sentence not supported by its source: {why}", **loc))
    # LLM judge (strong tier) and OpenAI Moderation on top of the deterministic checks
    llm = get_llm()
    try:
        judged = llm.review(draft.model_dump(), {"rules": [r.model_dump() for r in res.rules], "precedents": [p.model_dump() for p in res.precedents]}, facts, raw_values or [])
        for it in judged.issues:
            issue = Issue(code=f"judge_{it.code}", message=it.message, section_id=it.section_id, sentence_index=it.sentence_index, blocking=it.code in BLOCKING_REVIEW_CODES)
            (blocking if issue.blocking else warnings).append(issue)
        flagged = llm.moderate(" ".join(s.text for sec in draft.sections for s in sec.sentences), raw_values or [])
        if flagged:
            blocking.append(Issue(code="moderation", message=f"Flagged by moderation: {', '.join(flagged)}"))
    except ProviderUnavailable:
        warnings.append(Issue(code="judge_unavailable", message="The AI reviewer was unavailable; only the automatic checks ran.", blocking=False))
    for ph in draft.placeholders:
        warnings.append(Issue(code="placeholder", message=f"Fill in {ph} before exporting", blocking=False))
    warnings.append(Issue(code="verify_grounds", message="Delete any ground that isn't true for you.", blocking=False))
    if injection_flags:
        warnings.append(Issue(code="injection_detected", message="The uploaded letter contained text that looked like instructions. It was ignored.", blocking=False))
    cited = [v for v in verdicts]
    score = sum(v.supported for v in cited) / len(cited) if cited else 1.0
    return Review(blocking_issues=blocking, warnings=warnings, verdicts=verdicts, score=round(score, 4))


def drops_from_review(draft: LetterDraft, rv: Review) -> list[str]:
    """Turn blocking issues into specific, checkable rewrite instructions (drop the offending argument)."""
    out = []
    for iss in rv.blocking_issues:
        if iss.section_id is None or iss.sentence_index is None:
            continue
        sec = next((s for s in draft.sections if s.id == iss.section_id), None)
        if sec and iss.sentence_index < len(sec.sentences):
            aid = sec.sentences[iss.sentence_index].argument_id
            if aid:
                out.append(aid if ":" in aid else f"legal:{aid}")
    return sorted(set(out))


__all__ = ["intake", "classify", "research", "write", "review", "drops_from_review", "CATEGORIES"]
