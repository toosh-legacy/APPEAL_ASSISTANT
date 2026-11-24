"""Offline deterministic provider (SPEC 8.3). No model: regex/keyword extraction, playbook-template
writing and dictionary query rewriting. Returns the same schema-valid outputs a real model would."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from appeal_core.kb import denial_codes, playbooks
from appeal_core.text_support import best_support, content_terms

# ------------------------------------------------------------------ extraction
_DATE_PATTERNS = [
    (re.compile(r"\b([A-Z][a-z]+ \d{1,2}, \d{4})\b"), "%B %d, %Y"),
    (re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b"), "%m/%d/%Y"),
    (re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"), "%Y-%m-%d"),
]
US_STATES = set(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split()
)
HINTS = {
    "insurer": "Usually the logo or name at the top of the letter, or the signature at the bottom.",
    "plan_type": "Look for words like 'employer', 'group', 'Marketplace', 'Medicare Advantage' or 'Medicaid'.",
    "state": "Look at the plan or member address, or a 'state' line near the top.",
    "claim_number": "Often labelled 'Claim number', 'Reference no.' or 'Case ID' near the top.",
    "member_id": "Often labelled 'Member ID' or 'Subscriber #'; it is also on your insurance card.",
    "service": "The treatment, test or item that was denied, often labelled 'Service'.",
    "date_of_service": "Labelled 'Date of service' or 'Service date'.",
    "notice_date": "The date printed at the top of the letter.",
    "denial_reason": "Usually a paragraph starting with 'Reason' or 'Summary of our decision'.",
    "denial_codes": "Short codes like CO-50, sometimes labelled 'Denial code' or 'Adjustment reason code'.",
}


def parse_date(s: str) -> str | None:
    for pat, fmt in _DATE_PATTERNS:
        m = pat.search(s)
        if m:
            try:
                return datetime.strptime(m.group(1), fmt).date().isoformat()
            except ValueError:
                continue
    return None


def _fv(value, conf):
    return {"value": value, "confidence": conf}


# Document titles that contain insurer-like words ("benefits", "health") but are not the insurer's name.
_DOC_TITLE = re.compile(
    r"(?i)explanation of (benefits|coverage)|not a bill|notice of|adverse (benefit )?determination|"
    r"appeal rights|summary of|claim (detail|statement)|important (information|notice)"
)


def _insurer(lines: list[str], text: str) -> tuple[str | None, float]:
    kw = re.compile(
        r"\b(health|insurance|plan|care|benefits?|partners|mutual|network|trust|assurance|blue|medical)\b",
        re.I,
    )
    for ln in lines[:4]:
        cand = ln.split("|")[0].strip()
        if _DOC_TITLE.search(cand):
            continue
        if cand and kw.search(cand) and not re.search(r"\[|\d{3}", cand) and len(cand) < 60:
            if cand.isupper():
                # prefer a mixed-case occurrence elsewhere in the letter
                m = re.search(re.escape(cand), text[len(ln) :], re.I)
                mixed = text[len(ln) + m.start() : len(ln) + m.end()] if m else None
                if mixed and not mixed.isupper():
                    return mixed, 0.9
                return cand.title(), 0.75
            return cand, 0.9
    return None, 0.0


def _plan_type(text: str) -> tuple[str | None, float]:
    t = text.lower()
    rules = [
        (r"medicare advantage|part c\b", "medicare_advantage", 0.95),
        (r"medicaid", "medicaid_managed_care", 0.95),
        (r"marketplace|individual (health )?(plan|coverage)|\baca\b", "individual_marketplace", 0.9),
        (r"self-funded|self funded|erisa", "employer_self_funded", 0.85),
        (r"employer|group (health )?plan|fully insured", "employer_fully_insured", 0.75),
    ]
    for pat, val, conf in rules:
        if re.search(pat, t):
            return val, conf
    return None, 0.0


def _state(text: str) -> tuple[str | None, float]:
    m = re.search(r"(?i)\bstate\s*[:\-]\s*([A-Z]{2})\b", text)
    if m and m.group(1).upper() in US_STATES:
        return m.group(1).upper(), 0.95
    for m in re.finditer(r",\s*([A-Z]{2})\s+(?:\[ZIP_\d+\]|\d{5})", text):
        if m.group(1) in US_STATES:
            return m.group(1), 0.85
    return None, 0.0


def _labelled(text: str, labels: str) -> str | None:
    m = re.search(rf"(?im)(?:{labels})\s*[:#]?\s*(.+?)\s*$", text)
    return m.group(1).strip() if m else None


# Column headers of claim tables (EOB-style statements), mapped to fields.
_TABLE_COLUMNS = {
    "date_of_service": re.compile(r"(?i)^(dates? of service|service dates?|dos|date\(s\) of service)$"),
    "service": re.compile(
        r"(?i)^(what you received|service( description)?|description( of service)?|procedure|item/service|treatment)$"
    ),
}


def _table_fields(lines: list[str]) -> dict[str, str]:
    """Reads the first data row under a header row of a '|' or tab separated table."""
    out: dict[str, str] = {}
    for i, ln in enumerate(lines[:-1]):
        sep = "|" if ln.count("|") >= 2 else ("\t" if ln.count("\t") >= 2 else None)
        if not sep:
            continue
        header = [c.strip() for c in ln.split(sep)]
        cols = {f: j for f, pat in _TABLE_COLUMNS.items() for j, h in enumerate(header) if pat.match(h)}
        if not cols:
            continue
        row = [c.strip() for c in lines[i + 1].split(sep)]
        if len(row) != len(header):
            continue
        for f, j in cols.items():
            if row[j]:
                out.setdefault(f, row[j])
        if out:
            return out
    return out


# A short heading line (no final period) that introduces the reason paragraph on the next line.
_REASON_HEADING = re.compile(
    r"(?i)^(summary of (?:our|the) decision|why (?:this|your|the) (?:claim|request|service)[\w ]* (?:not paid|denied|not approved)|"
    r"reasons? for (?:this|our|the) decision|why we (?:denied|did not pay)[\w ]*|our decision|explanation of (?:the )?denial)\s*:?$"
)


def offline_extract(text: str) -> dict[str, Any]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    f: dict[str, dict] = {}
    ins, c = _insurer(lines, text)
    f["insurer"] = _fv(ins, c)
    pt, c = _plan_type(text)
    f["plan_type"] = _fv(pt, c)
    st, c = _state(text)
    f["state"] = _fv(st, c)

    m = re.search(r"\[CLAIM_NUMBER_\d+\]", text)
    f["claim_number"] = _fv(m.group(0) if m else None, 0.95 if m else 0.0)
    m = re.search(r"\[MEMBER_ID_\d+\]", text)
    f["member_id"] = _fv(m.group(0) if m else None, 0.95 if m else 0.0)

    table = _table_fields(lines)
    svc = _labelled(text, r"item/service|service(?! date)(?! dates)|services? (?:requested|denied)|treatment")
    conf = 0.9 if svc else 0.0
    if svc and (re.match(r"(?i)date", svc) or svc.startswith(("|", "\t"))):  # a table header row, not a value
        svc = None
    if not svc and table.get("service"):
        svc, conf = table["service"], 0.85
    if not svc:
        m = re.search(
            r"(?i)(?:for|of) ((?:[a-z][\w\-()]*\s){0,5}[a-z][\w\-()]*) (?:was|is|requires|does)", text
        )
        svc, conf = (m.group(1), 0.5) if m else (None, 0.0)
    f["service"] = _fv(svc, conf)

    dos_line = _labelled(text, r"date of service|service date")
    dos = parse_date(dos_line or "")
    conf = 0.9 if dos else 0.0
    if not dos and table.get("date_of_service"):
        dos = parse_date(table["date_of_service"])
        conf = 0.85 if dos else 0.0
    f["date_of_service"] = _fv(dos, conf)

    nd_line = _labelled(text, r"notice date|date of notice|letter date|date")
    nd = parse_date(nd_line or "") if nd_line else None
    conf = 0.9 if nd else 0.0
    if not nd:
        for ln in lines[:8]:
            if parse_date(ln) and len(ln) <= 25:
                nd, conf = parse_date(ln), 0.8
                break
    f["notice_date"] = _fv(nd, conf)

    # label must start the line and be followed by ':' (so "Adjustment reason code(s): CO-50" is not a reason)
    m = re.search(r"(?im)^\s*(?:reason for (?:the )?denial|denial reason|reason)\s*:\s*(.+?)\s*$", text)
    reason = m.group(1).strip() if m else None
    conf = 0.9 if reason else 0.0
    if not reason:
        for i, ln in enumerate(lines[:-1]):
            if _REASON_HEADING.match(ln):
                reason, conf = lines[i + 1], 0.85
                break
    if not reason:
        m = re.search(
            r"(?i)([^.\n]*\b(denied|not covered|not medically necessary|not approved)\b[^.\n]*\.)", text
        )
        reason, conf = (m.group(1).strip(), 0.5) if m else (None, 0.0)
    f["denial_reason"] = _fv(reason, conf)

    codes = sorted(set(re.findall(r"\b(?:CO|PR|OA|PI|CR)-\d{1,3}\b", text)))
    f["denial_codes"] = _fv(codes, 0.95 if codes else 0.6)

    for k, v in f.items():
        v["hint"] = HINTS.get(k)
    missing = [k for k, v in f.items() if not v["value"] and k != "denial_codes"]
    return {
        "fields": f,
        "missing_fields": missing,
        "plan_type": f["plan_type"]["value"],
        "state": f["state"]["value"],
    }


# ------------------------------------------------------------------ query rewriting
SYNONYMS = {
    "medical_necessity": [
        "not medically necessary",
        "medical necessity criteria",
        "medically necessary treatment",
    ],
    "prior_authorization": ["prior authorization precertification", "approval before service"],
    "out_of_network": ["out-of-network emergency services", "nonparticipating provider"],
    "experimental_investigational": ["experimental investigational treatment", "unproven treatment evidence"],
    "not_covered_benefit": ["excluded benefit coverage", "plan provisions coverage"],
    "coding_billing_error": ["claim billing information", "claim submission error"],
    "timely_filing": ["claim filing time limit", "late claim submission"],
    "deadline": [
        "time to file appeal",
        "days following receipt of notification adverse benefit determination",
    ],
    "external review": ["independent external review", "independent review organization"],
}


# Plain-language -> regulatory vocabulary. Each matched concept appends its legal terms to the query
# (variant 2) and contributes a short legal-concept query (variant 3). The original query always stays first.
CONCEPTS: list[tuple[str, str]] = [
    (
        r"deadline|how long|how many days|time limit|timeframe|time frame",
        "days following receipt of notification filed within calendar days",
    ),
    (r"external review|independent review", "external review independent review organization"),
    (r"cop(y|ies)|documents|records|my file", "reasonable access free of charge documents records relevant"),
    (
        r"doctor|health care professional|expert|specialist",
        "consult health care professional appropriate training experience medical judgment",
    ),
    (r"job|employer|work", "group health plan"),
    (r"marketplace|individual", "individual health insurance coverage issuer"),
    (r"medicare advantage|\bma\b", "MA organization enrollee organization determination"),
    (r"medicaid", "MCO PIHP PAHP enrollee"),
    (r"surprise|balance bill", "nonparticipating provider balance billing"),
    (r"emergenc", "emergency services emergency medical condition"),
    (r"urgent|fast|expedited", "urgent care expedited"),
    (r"notice|letter|explain", "notification adverse benefit determination"),
    (r"denial|denied|deny", "adverse benefit determination"),
    (r"pending|while .* appeal|keep (getting|my)", "continued coverage pending outcome"),
    (r"medical necessity|medically necessary", "medical necessity medical judgment"),
    (r"experimental|investigational", "experimental investigational medical judgment"),
]


def offline_rewrite(query: str) -> list[str]:
    q = query.lower()
    hits = [terms for pat, terms in CONCEPTS if re.search(pat, q)]
    for key, syns in SYNONYMS.items():  # category keys used by the Research agent
        if key in q or key.replace("_", " ") in q:
            hits.append(syns[0])
    if not hits:
        return [query]
    expansion = " ".join(dict.fromkeys(" ".join(hits).split()))
    return [query, f"{query} {expansion}", hits[0]]


# ------------------------------------------------------------------ writing
NON_BINDING = "Independent reviewers in similar California cases have found"


_FAVORABLE = re.compile(
    r"(is|was|are|were) (medically necessary|likely to be more beneficial|appropriate|indicated|warranted)",
    re.I,
)


def _first_sentence(excerpt: str, max_words: int = 40) -> str | None:
    """The reviewer's favorable conclusion sentence, quoted (grounded by construction)."""
    t = re.sub(r"\s+", " ", excerpt.strip())
    for sent in re.split(r"(?<=[.!?])\s+", t):
        s = re.sub(
            r"^(Findings:|Final Result:|Therefore,|Thus,|Accordingly,|In conclusion,|For (?:these|this) reasons?,|As such,)\s*",
            "",
            sent.strip(),
            flags=re.I,
        )
        s = re.sub(r"^the (physician )?reviewers? (found|determined) that\s*", "", s, flags=re.I)
        if (
            _FAVORABLE.search(s)
            and not re.search(r"\bnot\b", s, re.I)
            and 6 <= len(s.split()) <= max_words
            and ":" not in s
        ):
            return s.rstrip(".")
    return None


def human_date(iso: str | None) -> str | None:
    if not iso or not re.match(r"\d{4}-\d{2}-\d{2}$", str(iso)):
        return iso
    d = datetime.strptime(iso, "%Y-%m-%d")
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def _pick_rule(needs: str, rules: list[dict], min_score: float = 0.25) -> tuple[str | None, float]:
    best = best_support(needs, [(r["cite_id"], (r.get("heading") or "") + " " + r["text"]) for r in rules])
    if best and best[1] >= min_score:
        return best[0], best[1]
    return None, 0.0


def offline_write(req: dict[str, Any]) -> dict[str, Any]:
    facts = req["facts"]
    cat = req["category"]
    plan_type = facts.get("plan_type")
    pb = playbooks()[cat]
    rules = req.get("rules", [])
    precedents = req.get("precedents", [])
    deadlines = req.get("deadlines", [])
    drop = set(req.get("drop_sentences", []))
    svc = facts.get("service") or "[ADD: the service that was denied]"
    insurer = facts.get("insurer") or "[ADD: your insurance company]"
    nd = human_date(facts.get("notice_date"))
    placeholders: list[str] = []

    def ph(text: str) -> None:
        for m in re.findall(r"\[ADD: [^\]]+\]", text):
            if m not in placeholders:
                placeholders.append(m)

    sections: list[dict] = []
    header = [
        {"text": f"Member: {facts.get('member_name') or '[ADD: your full name]'}", "kind": "header"},
        {"text": f"Member ID: {facts.get('member_id') or '[ADD: member ID]'}", "kind": "header"},
        {
            "text": f"Claim or reference number: {facts.get('claim_number') or '[ADD: claim number]'}",
            "kind": "header",
        },
        {
            "text": f"Date of service: {human_date(facts.get('date_of_service')) or '[ADD: date of service]'}",
            "kind": "header",
        },
        {"text": f"RE: Appeal of the denial of {svc}", "kind": "header"},
    ]
    sections.append({"id": "header", "title": "Header", "sentences": header})

    intro = [
        {
            "text": f"I am writing to appeal {insurer}'s decision dated {nd or '[ADD: date of the denial letter]'} to deny coverage for {svc}.",
            "kind": "fact",
        },
        {
            "text": f'The reason given for the denial was: "{facts.get("denial_reason") or "[ADD: the reason given in the letter]"}"',
            "kind": "fact",
        },
    ]
    sections.append({"id": "intro", "title": "Introduction", "sentences": intro})

    # Legal grounds: only sentences whose needs are supported by a retrieved rule
    legal = []
    for arg in pb.get("legal", []):
        if plan_type and plan_type not in arg.get("plan_types", []):
            continue
        if f"legal:{arg['id']}" in drop:
            continue
        cid, score = _pick_rule(arg["needs"] + " " + arg["text"], rules)
        if cid:
            legal.append({"text": arg["text"], "citations": [cid], "kind": "legal", "argument_id": arg["id"]})
    for d in deadlines:
        if not d.get("cite_id") or not d.get("letter_text") or "legal:deadline" in drop:
            continue
        legal.append(
            {
                "text": d["letter_text"],
                "citations": [d["cite_id"]],
                "kind": "legal",
                "argument_id": "deadline",
            }
        )
    if legal:
        sections.append({"id": "grounds", "title": "Why I am appealing", "sentences": legal})

    fact_sents = []
    for i, tmpl in enumerate(pb.get("facts", [])):
        if f"fact:{i}" in drop:
            continue
        fact_sents.append({"text": tmpl.format(service=svc), "kind": "fact", "argument_id": f"fact:{i}"})
    sections.append({"id": "facts", "title": "About my care", "sentences": fact_sents})

    prec = []
    supportive = [p for p in precedents if p.get("overturned")]
    for p in supportive[:2]:
        if f"precedent:{p['cite_id']}" in drop:
            continue
        quote = _first_sentence(p["excerpt"])
        if not quote:
            continue
        prec.append(
            {
                "text": f"{NON_BINDING} that {quote[0].lower() + quote[1:]}.",
                "citations": [p["cite_id"]],
                "kind": "precedent",
                "argument_id": f"precedent:{p['cite_id']}",
            }
        )
    if prec:
        prec.append(
            {
                "text": "I understand these decisions do not bind my plan, but I ask that you consider them.",
                "kind": "fact",
            }
        )
        sections.append({"id": "precedents", "title": "Similar independent reviews", "sentences": prec})

    request = [
        {"text": f"Please reverse the denial and approve coverage for {svc}.", "kind": "request"},
        {"text": "Please send your decision to me in writing.", "kind": "request"},
    ]
    sections.append({"id": "request", "title": "My request", "sentences": request})
    closing = [
        {"text": "Sincerely,", "kind": "closing"},
        {"text": facts.get("member_name") or "[ADD: your full name]", "kind": "closing"},
        {"text": "[ADD: your phone number or email]", "kind": "closing"},
    ]
    sections.append({"id": "closing", "title": "Closing", "sentences": closing})

    style = req.get("style")
    if style:
        sections = apply_style(sections, req.get("section_id"), style)
    for s in sections:
        for sent in s["sentences"]:
            sent.setdefault("citations", [])
            ph(sent["text"])
    return {
        "sections": sections,
        "placeholders": placeholders,
        "revision": req.get("revision", 0),
        "degraded": False,
    }


def apply_style(sections: list[dict], section_id: str | None, style: str) -> list[dict]:
    for s in sections:
        if section_id and s["id"] != section_id:
            continue
        if style == "shorter" and len(s["sentences"]) > 1:
            s["sentences"] = s["sentences"][: max(1, len(s["sentences"]) - 1)]
        elif style == "firmer":
            for sent in s["sentences"]:
                sent["text"] = (
                    sent["text"]
                    .replace("I ask that", "I request that")
                    .replace("I ask the plan to", "I request that the plan")
                    .replace("Please ", "I request that you ")
                )
                sent["text"] = re.sub(
                    r"I request that you (\w)",
                    lambda m: "I request that you " + m.group(1).lower(),
                    sent["text"],
                )
        elif style == "add_detail" and s["id"] == "facts":
            s["sentences"].append(
                {
                    "text": "[ADD: one or two sentences about your symptoms and the treatments you have already tried]",
                    "kind": "fact",
                }
            )
    return sections


def classify_by_codes(codes: list[str]) -> str | None:
    m = denial_codes()
    cats = {m[c] for c in codes if c in m}
    return cats.pop() if len(cats) == 1 else None


__all__ = ["offline_extract", "offline_write", "offline_rewrite", "content_terms", "parse_date"]
