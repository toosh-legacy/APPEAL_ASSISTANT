"""Deterministic support checking (SPEC 11.4, local): key-term overlap, number/date agreement and negation
checks between a sentence and its cited passages."""

from __future__ import annotations

import re

STOP = set(
    """a an the and or of to in on for with by at from as is are was were be been being this that these those it its
    i me my we our you your they their he she his her them us not no nor so than then there here which who whom whose
    what when where why how all any both each few more most other some such only own same too very can will just should
    would could may might must shall do does did done have has had having into over under again further once also please
    plan member claim""".split()
)
NEG = re.compile(r"\b(not|no|never|without|cannot|isn't|wasn't|don't|doesn't)\b", re.I)
NUM = re.compile(r"\b\d+(?:\.\d+)?\b")
TOKEN = re.compile(r"\[[A-Z_]+_\d+\]|\[ADD:[^\]]*\]")


def stem(w: str) -> str:
    w = w.lower()
    for suf in ("ations", "ation", "ingly", "ings", "ing", "edly", "ed", "ies", "es", "s", "ly"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def content_terms(text: str) -> set[str]:
    text = TOKEN.sub(" ", text)
    return {stem(w) for w in re.findall(r"[A-Za-z][A-Za-z\-]+", text) if w.lower() not in STOP and len(w) > 2}


def overlap(sentence: str, passage: str) -> float:
    s = content_terms(sentence)
    if not s:
        return 0.0
    p = content_terms(passage)
    return len(s & p) / len(s)


def best_support(sentence: str, passages: list[tuple[str, str]]) -> tuple[str, float] | None:
    best = None
    for pid, text in passages:
        sc = overlap(sentence, text)
        if best is None or sc > best[1]:
            best = (pid, sc)
    return best


def check_support(sentence: str, passages: list[str], min_overlap: float = 0.3, allowed_numbers: set[str] | None = None) -> tuple[bool, str, float]:
    joined = " ".join(passages)
    sc = overlap(sentence, joined)
    if sc < min_overlap:
        return False, f"low key-term overlap ({sc:.2f})", sc
    nums = set(NUM.findall(TOKEN.sub(" ", re.sub(r"\d{4}-\d{2}-\d{2}", " ", sentence))))
    pnums = set(NUM.findall(joined)) | (allowed_numbers or set())
    missing = nums - pnums
    if missing:
        return False, f"numbers not in source: {sorted(missing)}", sc
    if NEG.search(sentence) and not NEG.search(joined):
        return False, "negation in sentence not found in source", sc
    return True, "supported", sc
