import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.slow
def test_m1_training_is_reproducible():
    from appeal_ml import m1

    a = m1.train()
    b = m1.train()
    assert a["gold_macro_f1"] == b["gold_macro_f1"] and a["temperature"] == b["temperature"]


def test_model_cards_complete():
    for model in ["m1", "m2", "m3"]:
        card = ROOT / "ml" / "artifacts" / model / "v1" / "model_card.md"
        if not card.exists():
            pytest.skip("run `make train` first")
        text = card.read_text(encoding="utf-8")
        assert "## Limitations" in text
        assert (ROOT / "ml" / "artifacts" / model / "v1" / "training_config.json").exists()
    assert "synthetic" in (ROOT / "ml/artifacts/m1/v1/model_card.md").read_text(encoding="utf-8").lower()
    m3 = (ROOT / "ml/artifacts/m3/v1/model_card.md").read_text(encoding="utf-8")
    assert "leakage" in m3 and "Fairness" in m3


def test_m3_excludes_leaky_and_sensitive_features():
    p = ROOT / "ml/artifacts/m3/v1/metrics.json"
    if not p.exists():
        pytest.skip("run `make train` first")
    m = json.loads(p.read_text())
    for f in ["findings", "days_to_adopt", "age_range", "patient_gender"]:
        assert f not in m["features"]


def test_time_split_never_random():
    import pandas as pd
    from appeal_ml.m2 import time_split

    df = pd.DataFrame({"year": [y for y in range(2010, 2026) for _ in range(10)] + [2026] * 2})
    tr, va, te, split = time_split(df)
    assert tr.year.max() < va.year.min() < te.year.min()
    assert split["test_years"] == [2024, 2025] and 2026 in split["excluded_partial_years"]


def test_classifier_uses_code_override():
    from appeal_worker.agents import classify

    c = classify("Your claim was denied.", ["CO-197"], "MRI")
    assert c.category == "prior_authorization" and c.source == "denial_code"
