from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from appeal_core.deadlines import compute_deadlines, next_level_options
from appeal_core.kb import CATEGORIES, deadline_rules, playbooks, summary_chunks

ROOT = Path(__file__).resolve().parents[1]


def _letters(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_gold_letters_committed_and_balanced():
    gold = _letters(ROOT / "evals" / "gold" / "letters.jsonl")
    assert len(gold) == 120
    cats = [g["label"]["category"] for g in gold]
    assert {c: cats.count(c) for c in set(cats)} == {c: 15 for c in CATEGORIES}


def test_synthetic_identifiers_are_obviously_fake():
    for split in ["train", "validation"]:
        p = ROOT / "data" / "processed" / "letters" / f"{split}.jsonl"
        if not p.exists():
            continue
        for letter in _letters(p)[:500]:
            f = letter["label"]["fields"]
            assert f["member_id"].startswith("ZZTEST")
            assert re.search(r"555-01\d\d", letter["text"])
            assert "Example St" in letter["text"]
    for g in _letters(ROOT / "evals" / "gold" / "letters.jsonl"):
        assert g["label"]["fields"]["member_id"].startswith("ZZTEST")


def test_gold_templates_differ_from_train():
    gold = _letters(ROOT / "evals" / "gold" / "letters.jsonl")
    train_p = ROOT / "data" / "processed" / "letters" / "train.jsonl"
    if not train_p.exists():
        return
    train_reasons = {t["label"]["reason_text"] for t in _letters(train_p)}
    assert not ({g["label"]["reason_text"] for g in gold} & train_reasons)


def test_generator_is_deterministic():
    import random

    from appeal_synth.generate import make_letter

    a = make_letter(random.Random("x"), "train", 1)
    b = make_letter(random.Random("x"), "train", 1)
    assert a == b


def test_every_deadline_rule_is_cited():
    d = deadline_rules()
    for r in d["rules"] + d["next_levels"]:
        assert r["enabled"], r["id"]
        assert r["basis_chunk_id"].startswith("reg:")


def test_deadline_math():
    out = compute_deadlines("medicare_advantage", date(2025, 1, 31))
    assert out[0]["due_date"] == "2025-04-01"  # 60 calendar days
    out = compute_deadlines("employer_self_funded", date(2024, 2, 28))
    assert out[0]["due_date"] == "2024-08-26"  # 180 days, leap year
    assert compute_deadlines(None, date(2025, 1, 1)) == []
    assert compute_deadlines("medicaid_managed_care", None) == []


def test_next_levels_have_citations():
    for pt in ["employer_self_funded", "medicare_advantage", "medicaid_managed_care"]:
        opts = next_level_options(pt)
        assert opts and all(o["basis_chunk_id"] for o in opts)


def test_summaries_marked_for_review():
    chunks = summary_chunks()
    assert len(chunks) >= 10
    assert all(c["status"] == "needs_human_review" for c in chunks)


def test_playbooks_cover_all_categories():
    pb = playbooks()
    assert set(pb) == set(CATEGORIES)
    for b in pb.values():
        assert b["evidence"] and b["facts"]
