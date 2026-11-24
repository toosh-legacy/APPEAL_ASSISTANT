"""Units for the lite-mode vector store, calendar and PDF exports, Ragas sample building."""

from __future__ import annotations

import warnings

import numpy as np


def test_numpy_vector_store_search_and_filter(tmp_path):
    from appeal_core.retrieval.vectorstore import DIM, NumpyVectorStore

    rng = np.random.default_rng(0)
    vecs = rng.normal(size=(3, DIM)).tolist()
    s = NumpyVectorStore("t", root=tmp_path)
    s.add(["a", "b", "c"], vecs, ["x", "y", "z"], [{"type": "Medical Necessity"}, {"type": "Urgent Care"}, {"type": "Medical Necessity"}])
    assert [i for i, _ in s.search(vecs[1], k=1)] == ["b"]
    hits = s.search(vecs[1], k=3, filter={"type": {"$eq": "Medical Necessity"}})
    assert {i for i, _ in hits} == {"a", "c"}
    assert NumpyVectorStore("t", root=tmp_path).existing_ids() == {"a", "b", "c"}  # persisted


def test_ics_has_all_day_event_reminders_and_dtstamp():
    from appeal_core.deadlines import ics_for

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        s = ics_for({"due_date": "2026-05-20", "label": "ERISA internal appeal", "basis_citation": "29 CFR 2560.503-1(h)(3)(i)"}, "case-1")
    assert "DTSTART;VALUE=DATE:20260520" in s and "DTSTAMP:" in s and s.count("BEGIN:VALARM") == 2
    assert "UID:case-1@appeal-assistant.local" in s and "29 CFR 2560.503-1(h)(3)(i)" in s


def test_pdf_export_numbers_footnotes():
    from appeal_api.exports import _html, render_pdf

    view = {"sections": [{"id": "grounds", "sentences": [{"text": "I ask for a full & fair review.", "citations": ["R1"]}]}], "sources": {"R1": {"citation": "29 CFR 2560.503-1(h)"}}}
    html = _html(view)
    assert "<sup>1</sup>" in html and "full &amp; fair" in html and "<li>29 CFR 2560.503-1(h)</li>" in html
    assert render_pdf(view)[:5] == b"%PDF-"


def test_ragas_samples_skip_letters_with_raw_identifiers():
    from appeal_evals.ragas_eval import samples_from

    base = {
        "status": "READY",
        "category": "medical_necessity",
        "g": {"label": {"fields": {"service": "MRI"}, "reason_text": "Not medically necessary."}},
        "research": {"rules": [{"text": "A plan must ..."}], "precedents": [{"excerpt": "Reviewers found ..."}]},
    }
    ok = {**base, "sections": [{"id": "intro", "sentences": [{"text": "Member [MEMBER_ID_1] appeals."}]}]}
    leaky = {**base, "sections": [{"id": "intro", "sentences": [{"text": "Member ZZTEST123456 appeals."}]}]}
    got = samples_from([ok, leaky])
    assert len(got) == 1 and got[0]["retrieved_contexts"] == ["A plan must ...", "Reviewers found ..."]
