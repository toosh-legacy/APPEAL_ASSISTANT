"""M2: IMR-type text classifier (real DMHC Findings text -> Type), time-based split, shortcut ablation."""

from __future__ import annotations

import re

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, recall_score
from sklearn.pipeline import Pipeline

from appeal_ml.common import ROOT, SEED, artifact_dir, file_hash, git_sha, save_json

DATA = ROOT / "data" / "processed" / "imr.parquet"
VERSION = "v1"

# Phrases that state the label directly (shortcut features) - removed in the ablation run.
SHORTCUTS = re.compile(
    r"experimental(ly)?|investigational|investigative|medically necessary|medical(ly)? necessity|not medically|"
    r"urgent(ly)?|emergen\w*|nature of statutory criteria|statutory criteria|likely to be more beneficial|"
    r"standard therapies|clinical trials?",
    re.I,
)


def time_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    counts = df.year.value_counts()
    full_years = sorted(y for y in counts.index if counts[y] >= 0.5 * counts.median())
    Y = full_years[-1]  # most recent full year
    if counts.get(df.year.max(), 0) < 0.5 * counts.median():
        Y = max(y for y in full_years if y < df.year.max())
    test_years = [Y - 1, Y]
    val_year = Y - 2
    train = df[df.year <= Y - 3]
    val = df[df.year == val_year]
    test = df[df.year.isin(test_years)]
    return train, val, test, {"train_years": f"{int(df.year.min())}-{Y - 3}", "validation_year": int(val_year), "test_years": test_years, "excluded_partial_years": sorted(int(y) for y in counts.index if y > Y)}


def clean_text(s: str) -> str:
    s = re.sub(r"Credentials/Qualifications:.*$", "", s or "", flags=re.S)
    return s


def strip_shortcuts(s: str) -> str:
    return SHORTCUTS.sub(" ", s)


def tfidf_lr() -> Pipeline:
    return Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=3, max_features=200_000, sublinear_tf=True, stop_words="english")),
            ("clf", LogisticRegression(C=4.0, max_iter=2000, class_weight="balanced", random_state=SEED)),
        ]
    )


class M2Model:
    def __init__(self, pipe: Pipeline):
        self.pipe = pipe

    def predict_one(self, text: str) -> str:
        return str(self.pipe.predict([strip_shortcuts(text)])[0])


def _scores(y, pred, labels) -> dict:
    return {
        "macro_f1": float(f1_score(y, pred, average="macro")),
        "per_class_recall": {c: float(v) for c, v in zip(labels, recall_score(y, pred, labels=labels, average=None, zero_division=0), strict=True)},
    }


def _embeddings(ref_ids: list[str]) -> np.ndarray | None:
    """Reuse the precedent_chunk embeddings (first chunk of each case) computed by the data pipeline."""
    try:
        from appeal_core.db import get_engine
        from sqlalchemy import text

        with get_engine().connect() as c:
            rows = c.execute(text("SELECT reference_id, embedding::text FROM precedent_chunk WHERE id LIKE '%#0' AND embedding IS NOT NULL")).all()
        m = {r[0]: np.fromstring(r[1].strip("[]"), sep=",", dtype=np.float32) for r in rows}
        if len(m) < 0.9 * len(ref_ids):
            return None
        return np.stack([m.get(r, np.zeros(384, dtype=np.float32)) for r in ref_ids])
    except Exception:
        return None


def train() -> dict:
    df = pd.read_parquet(DATA)
    df = df[df.type.notna() & df.findings.notna()].copy()
    df["text"] = df.findings.map(clean_text)
    tr, va, te, split = time_split(df)
    labels = sorted(df.type.unique())
    out: dict = {"split": split, "labels": labels, "sizes": {"train": len(tr), "validation": len(va), "test": len(te)}}
    # baseline: majority class
    maj = tr.type.mode()[0]
    out["baseline_majority"] = _scores(te.type, [maj] * len(te), labels)

    full = tfidf_lr().fit(tr.text, tr.type)
    out["tfidf_lr"] = {"validation": _scores(va.type, full.predict(va.text), labels), "test": _scores(te.type, full.predict(te.text), labels)}
    ablated = tfidf_lr().fit(tr.text.map(strip_shortcuts), tr.type)
    out["tfidf_lr_shortcuts_removed"] = {
        "validation": _scores(va.type, ablated.predict(va.text.map(strip_shortcuts)), labels),
        "test": _scores(te.type, ablated.predict(te.text.map(strip_shortcuts)), labels),
    }
    emb = _embeddings(df.reference_id.tolist())
    if emb is not None:
        idx = {r: i for i, r in enumerate(df.reference_id)}
        Xtr, Xva, Xte = (emb[[idx[r] for r in d.reference_id]] for d in (tr, va, te))
        lr = LogisticRegression(C=2.0, max_iter=3000, class_weight="balanced", random_state=SEED).fit(Xtr, tr.type)
        out["embeddings_lr"] = {"validation": _scores(va.type, lr.predict(Xva), labels), "test": _scores(te.type, lr.predict(Xte), labels), "note": "MiniLM embeddings of the first precedent chunk (shortcut phrases NOT removed)"}
    else:
        out["embeddings_lr"] = {"skipped": "precedent embeddings not available"}
    d = artifact_dir("m2", VERSION)
    # serving model = shortcut-removed TF-IDF (the user's reason text never contains reviewer boilerplate)
    joblib.dump(M2Model(ablated), d / "model.joblib")
    save_json(d / "metrics.json", out)
    save_json(d / "training_config.json", {"seed": SEED, "git_sha": git_sha(), "data_hashes": {"imr.parquet": file_hash(DATA)}, "split": split, "serving_variant": "tfidf_lr_shortcuts_removed"})
    (d / "model_card.md").write_text(card(out), encoding="utf-8")
    return out


def card(m: dict) -> str:
    def row(name, r):
        if "test" not in r:
            return f"| {name} | n/a | n/a | {r.get('skipped', '')} |"
        return f"| {name} | {r['validation']['macro_f1']:.3f} | {r['test']['macro_f1']:.3f} | {', '.join(f'{k}: {v:.2f}' for k, v in r['test']['per_class_recall'].items())} |"

    full_f1 = m["tfidf_lr"]["test"]["macro_f1"]
    abl_f1 = m["tfidf_lr_shortcuts_removed"]["test"]["macro_f1"]
    if abl_f1 >= full_f1 - 0.01:
        interp = (
            f"removing the label-stating phrases did NOT lower test macro-F1 ({full_f1:.3f} -> {abl_f1:.3f}). The shortcut is not only in those "
            "phrases: DMHC writes each IMR type with a different template (for example 'Nature of Statutory Criteria/Case Summary' sections and "
            "'standard therapy' comparisons), so the remaining structure still gives the type away. The high score therefore measures template "
            "recognition more than clinical understanding. A stronger test (Phase B) trains only on the case-summary sentences before the reviewer's "
            "conclusion, or on the user's own denial wording."
        )
    else:
        interp = f"removing the label-stating phrases lowered test macro-F1 from {full_f1:.3f} to {abl_f1:.3f}; the difference is the part of the score that came from the shortcut."
    return f"""# Model card: M2 IMR-type text classifier ({VERSION})

## What it does
Predicts the DMHC IMR `Type` ({", ".join(m["labels"])}) from text. Trained on the physician reviewers' `Findings` text of real California IMR decisions (California Department of Managed Health Care, CC BY). The Research agent uses it to choose which precedent pool fits the user's case.

## Split (time-based, never random)
Train: {m["split"]["train_years"]}; validation: {m["split"]["validation_year"]}; test: {m["split"]["test_years"]} (the two most recent full years). Partial years excluded: {m["split"]["excluded_partial_years"]}.
A random split would leak the future into the past: reviewer templates, wording and the mix of treatments change over the years (e.g. new drug classes, new boilerplate), so a random split overstates how well the model works on next year's cases. The time split mirrors deployment: train on the past, predict the future.

Sizes: {m["sizes"]}

## Results (macro-F1)
| Variant | Validation | Test | Test per-class recall |
|---|---:|---:|---|
| Majority-class baseline | - | {m["baseline_majority"]["macro_f1"]:.3f} | |
{row("TF-IDF + logistic regression", m["tfidf_lr"])}
{row("TF-IDF + LR, label-stating phrases removed (shortcut ablation)", m["tfidf_lr_shortcuts_removed"])}
{row("MiniLM embeddings + logistic regression", m["embeddings_lr"])}

## Shortcut learning
Findings text often states the label in boilerplate ("...is not medically necessary...", "...is likely to be more beneficial than any available standard therapy..." for experimental cases). The full model can score highly just by spotting these phrases. The ablation removes them (regex in `m2.py`) and re-trains; the drop between the two rows measures how much the model relied on the shortcut. The **served** model is the shortcut-removed variant, because the user's denial text does not contain reviewer boilerplate.

**What the ablation showed:** {interp}

## Limitations
- Trained on reviewer findings, applied to the user's redacted reason + service text: a domain shift. Used only to pick a precedent pool, never shown as a prediction.
- Urgent Care is a small class; its recall is noisy.
- California only.
"""
