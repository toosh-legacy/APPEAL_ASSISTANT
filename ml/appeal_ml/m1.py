"""M1: denial-category classifier on synthetic letters (8 categories)."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from appeal_core.kb import CATEGORIES
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix, f1_score, recall_score
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

from appeal_ml.common import ROOT, SEED, artifact_dir, ece, file_hash, git_sha, reliability_plot, save_json

TRAIN = ROOT / "data" / "processed" / "letters" / "train.jsonl"
VAL = ROOT / "data" / "processed" / "letters" / "validation.jsonl"
GOLD = ROOT / "evals" / "gold" / "letters.jsonl"
VERSION = "v1"


def load(path: Path) -> pd.DataFrame:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        d = json.loads(line)
        lab = d["label"]
        svc = lab["fields"]["service"]
        template = lab["reason_text"].replace(svc, "{service}").replace(svc[0].upper() + svc[1:], "{service}")
        rows.append({"reason": lab["reason_text"], "codes": " ".join(lab["fields"]["denial_codes"]) or "NOCODE", "y": lab["category"], "template": template})
    return pd.DataFrame(rows)


def features(with_codes: bool = True) -> ColumnTransformer:
    tf = [
        ("word", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1), "reason"),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=2), "reason"),
    ]
    if with_codes:
        tf.append(("codes", CountVectorizer(token_pattern=r"[A-Z]+-?\d*", lowercase=False, binary=True), "codes"))
    return ColumnTransformer(tf)


def candidates(with_codes: bool = True) -> dict[str, Pipeline]:
    return {
        "logreg": Pipeline([("f", features(with_codes)), ("clf", LogisticRegression(C=4.0, max_iter=3000, random_state=SEED))]),
        "linear_svm_calibrated": Pipeline([("f", features(with_codes)), ("clf", CalibratedClassifierCV(LinearSVC(C=0.5, random_state=SEED), cv=3, method="sigmoid"))]),
    }


def temperature_scale(p: np.ndarray, T: float) -> np.ndarray:
    z = np.log(np.clip(p, 1e-12, 1)) / T
    z -= z.max(1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(1, keepdims=True)


def fit_temperature(p: np.ndarray, y_idx: np.ndarray) -> float:
    best, bestT = 1e9, 1.0
    for T in np.exp(np.linspace(np.log(0.25), np.log(8.0), 60)):
        q = temperature_scale(p, T)
        nll = -np.log(np.clip(q[np.arange(len(y_idx)), y_idx], 1e-12, 1)).mean()
        if nll < best:
            best, bestT = nll, float(T)
    return bestT


class M1Model:
    """Serving wrapper: temperature-calibrated probabilities over the 8 categories."""

    def __init__(self, est, threshold: float, temperature: float = 1.0):
        self.est = est
        self.threshold = threshold
        self.temperature = temperature
        self.classes_ = est.classes_

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return temperature_scale(self.est.predict_proba(X), self.temperature)

    def predict_proba_one(self, reason: str, codes: list[str]) -> dict[str, float]:
        X = pd.DataFrame([{"reason": reason or "", "codes": " ".join(codes) or "NOCODE"}])
        p = self.predict_proba(X)[0]
        return {c: float(v) for c, v in zip(self.classes_, p, strict=True)}


def coverage_threshold(probs: np.ndarray, correct: np.ndarray, target: float = 0.95) -> tuple[float, float, list[dict]]:
    curve = []
    best = None
    for t in np.round(np.arange(0.30, 0.995, 0.01), 2):
        ans = probs >= t
        cov = float(ans.mean())
        acc = float(correct[ans].mean()) if ans.any() else 1.0
        curve.append({"threshold": float(t), "coverage": cov, "accuracy": acc})
        if best is None and acc >= target:
            best = (float(t), cov)
    return (best or (0.99, float((probs >= 0.99).mean()))) + (curve,)


def train() -> dict:
    tr, va, gold = load(TRAIN), load(VAL), load(GOLD)
    results = {}
    fitted = {}
    for name, pipe in candidates().items():
        pipe.fit(tr[["reason", "codes"]], tr.y)
        pred = pipe.predict(va[["reason", "codes"]])
        results[name] = float(f1_score(va.y, pred, average="macro"))
        fitted[name] = pipe
    best_name = max(results, key=results.get)
    best = fitted[best_name]
    # Validation letters share templates with training letters, so validation scores are optimistic.
    # Calibration and the ask-user threshold are therefore fitted on GROUPED out-of-fold predictions
    # (groups = reason template): each fold predicts phrasings the model never saw, like real letters.
    from sklearn.model_selection import StratifiedGroupKFold, cross_val_predict

    allx = pd.concat([tr, va], ignore_index=True)
    oof = cross_val_predict(candidates()[best_name], allx[["reason", "codes"]], allx.y, groups=allx.template, cv=StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=SEED), method="predict_proba")
    classes = np.array(sorted(allx.y.unique()))
    y_idx = np.searchsorted(classes, allx.y.values)
    T = fit_temperature(oof, y_idx)
    cal = M1Model(best, 0.0, T)
    d = artifact_dir("m1", VERSION)
    oof_cal = temperature_scale(oof, T)
    conf_raw, conf = oof.max(1), oof_cal.max(1)
    corr_raw = classes[oof.argmax(1)] == allx.y.values
    corr = classes[oof_cal.argmax(1)] == allx.y.values
    reliability_plot(conf, corr, d / "reliability_validation.png", "M1 reliability (grouped OOF, temperature-scaled)")
    thr, cov, curve = coverage_threshold(conf, corr)
    cal.threshold = thr

    # gold evaluation (different templates/phrasing -> generalization)
    pg = cal.predict_proba(gold[["reason", "codes"]])
    gpred = cal.classes_[pg.argmax(1)]
    gold_conf = pg.max(1)
    gcorr = gpred == gold.y.values
    reliability_plot(gold_conf, gcorr, d / "reliability_gold.png", "M1 reliability (gold, calibrated)")
    answered = gold_conf >= thr
    metrics = {
        "selected_model": best_name,
        "validation_macro_f1": results,
        "oof_ece_raw": ece(conf_raw, corr_raw),
        "temperature": T,
        "oof_macro_f1_unseen_templates": float(f1_score(allx.y, classes[oof.argmax(1)], average="macro")),
        "oof_ece_calibrated": ece(conf, corr),
        "ask_user_threshold": thr,
        "oof_coverage_at_threshold": cov,
        "gold_macro_f1": float(f1_score(gold.y, gpred, average="macro")),
        "gold_per_class_recall": {c: float(v) for c, v in zip(CATEGORIES, recall_score(gold.y, gpred, labels=CATEGORIES, average=None, zero_division=0), strict=True)},
        "gold_ece": ece(gold_conf, gcorr),
        "gold_coverage_at_threshold": float(answered.mean()),
        "gold_accuracy_when_answered": float(gcorr[answered].mean()) if answered.any() else None,
        "gold_confusion_matrix": {"labels": CATEGORIES, "matrix": confusion_matrix(gold.y, gpred, labels=CATEGORIES).tolist()},
    }
    # ablation: without denial codes
    abl = candidates(with_codes=False)[best_name]
    abl.fit(tr[["reason", "codes"]], tr.y)
    metrics["ablation_no_codes"] = {
        "validation_macro_f1": float(f1_score(va.y, abl.predict(va[["reason", "codes"]]), average="macro")),
        "gold_macro_f1": float(f1_score(gold.y, abl.predict(gold[["reason", "codes"]]), average="macro")),
    }
    metrics["coverage_curve_validation"] = curve[::5]
    joblib.dump(cal, d / "model.joblib")
    save_json(d / "metrics.json", metrics)
    save_json(
        d / "training_config.json",
        {"seed": SEED, "git_sha": git_sha(), "data_hashes": {"train": file_hash(TRAIN), "validation": file_hash(VAL), "gold": file_hash(GOLD)}, "candidates": list(results), "calibration": "temperature scaling on grouped (by reason template) out-of-fold predictions"},
    )
    (d / "model_card.md").write_text(model_card(metrics, classification_report(gold.y, gpred, zero_division=0)), encoding="utf-8")
    return metrics


def model_card(m: dict, report: str) -> str:
    return f"""# Model card: M1 denial-category classifier ({VERSION})

## What it does
Predicts one of 8 denial categories from the (redacted) denial-reason text plus denial-code indicator features. Used by the Classifier agent; below the "ask the user" threshold the user picks the category (NEEDS_CATEGORY).

## Training data — read this first
**M1 is trained and evaluated only on synthetic letters** generated by `data/synth` (3,000 train / 500 validation), and evaluated on 120 gold synthetic letters that use different templates and phrasings. Real denial letters are messier (OCR noise, unusual wording, multiple reasons in one letter, insurer-specific jargon). **Expect a real-world gap**: scores on real letters will be lower than the numbers below. Phase B/C closes the gap by collecting consented, de-identified user corrections from the fact-confirmation screen (F2 AC3) as labeled examples and re-training.

## Features
TF-IDF word 1-2-grams and character 3-5-grams of the reason text; binary indicators for denial codes (e.g. CO-50).

## Models compared (validation macro-F1)
{json.dumps(m["validation_macro_f1"], indent=1)}

Selected: **{m["selected_model"]}**.

Validation letters come from the same template family as training letters, so validation macro-F1 is optimistic (it is ~1.0). A more honest in-training estimate uses grouped out-of-fold predictions where each fold holds out whole reason templates: OOF macro-F1 on unseen templates = **{m["oof_macro_f1_unseen_templates"]:.3f}**.

## Calibration
Temperature scaling (T = {m["temperature"]:.2f}) fitted on the grouped out-of-fold predictions.
- OOF ECE before: {m["oof_ece_raw"]:.4f}; after: {m["oof_ece_calibrated"]:.4f}
- Gold ECE (calibrated): {m["gold_ece"]:.4f}
- Reliability diagrams: `reliability_validation.png` (OOF), `reliability_gold.png`

## Ask-the-user threshold
Chosen from the OOF coverage-vs-accuracy curve as the lowest threshold where answered cases reach ≥ 95% accuracy: **{m["ask_user_threshold"]:.2f}** (OOF coverage {m["oof_coverage_at_threshold"]:.1%}). On gold: coverage {m["gold_coverage_at_threshold"]:.1%}, accuracy when answered {m["gold_accuracy_when_answered"]}.

## Gold results
- Macro-F1: **{m["gold_macro_f1"]:.3f}**
- Per-class recall: {json.dumps({k: round(v, 3) for k, v in m["gold_per_class_recall"].items()})}

```
{report}
```

## Ablation: denial codes (leakage discussion)
Without the code features: validation macro-F1 {m["ablation_no_codes"]["validation_macro_f1"]:.3f}, gold macro-F1 {m["ablation_no_codes"]["gold_macro_f1"]:.3f}. In the synthetic generator a code is present in ~60% of letters and always matches the category, so codes are close to a label leak; real letters often carry generic or wrong codes. The Classifier agent therefore uses the code map only as a high-precision override, and flags cases where the model disagrees with probability > 0.9.

## Limitations
- Synthetic-only training data (see above); English only; one reason per letter.
- Categories are our own taxonomy, not an industry standard.
- Not used to give advice; only to pick which playbook and rules to retrieve.
"""
