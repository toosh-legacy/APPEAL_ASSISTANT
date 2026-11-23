"""Data tests over data/processed (SPEC 17.1 'Data' row)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from appeal_core.privacy.pii import regex_detect

ROOT = Path(__file__).resolve().parents[1]
IMR = ROOT / "data" / "processed" / "imr.parquet"
REG = ROOT / "data" / "processed" / "regulation_chunks.json"


@pytest.fixture(scope="module")
def imr_df():
    if not IMR.exists():
        pytest.skip("run `make data` first")
    return pd.read_parquet(IMR)


def test_imr_schema(imr_df):
    for c in ["reference_id", "year", "treatment_category", "type", "overturned", "findings", "findings_original"]:
        assert c in imr_df.columns


def test_imr_no_duplicate_ids(imr_df):
    assert imr_df.reference_id.is_unique


def test_imr_row_count_bounds(imr_df):
    manifest = json.loads((ROOT / "data" / "manifest.json").read_text())
    if manifest["datasets"]["imr"]["source"] == "real":
        assert 30_000 <= len(imr_df) <= 200_000
    else:
        assert len(imr_df) == 2000


def test_imr_overturned_matches_text(imr_df):
    assert (imr_df.overturned == imr_df.determination_text.str.contains("Overturned")).all()


def test_imr_years_plausible(imr_df):
    assert imr_df.year.between(2001, 2030).all()


def test_imr_masked_findings_have_no_regex_pii(imr_df):
    sample = imr_df.findings.dropna().sample(2000, random_state=1)
    hits = [s for t in sample for s in regex_detect(t) if s.entity in {"EMAIL", "US_SSN", "PHONE"}]
    assert hits == []


def test_regulation_chunks_have_citations():
    if not REG.exists():
        pytest.skip("run `make data` first")
    chunks = json.loads(REG.read_text(encoding="utf-8"))
    assert len(chunks) > 100
    ids = [c["id"] for c in chunks]
    assert len(ids) == len(set(ids))
    for c in chunks:
        assert c["citation_path"].split(" CFR ")[0].isdigit()
        assert c["text"].strip()
        assert c["plan_types"]
    sources = {c["source_id"] for c in chunks}
    assert {"29cfr2560.503-1", "45cfr147.136", "42cfr422.M", "42cfr438.F"} <= sources


def test_manifest_has_hashes():
    m = json.loads((ROOT / "data" / "manifest.json").read_text())
    for name in ["imr", "ecfr"]:
        assert len(m["datasets"][name]["sha256"]) == 64


def test_raw_files_are_gitignored():
    gi = (ROOT / ".gitignore").read_text()
    assert "data/raw/*" in gi
