"""M3: overturn-rate model on structured DMHC fields, with baselines and fairness slices."""

from __future__ import annotations

import joblib
import numpy as np
import pandas as pd
from appeal_core.retrieval.stats import fit_beta_prior, smoothed_rate
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

from appeal_ml.common import ROOT, SEED, artifact_dir, file_hash, git_sha, save_json
from appeal_ml.m2 import time_split

DATA = ROOT / "data" / "processed" / "imr.parquet"
VERSION = "v1"
CATS = ["treatment_category", "treatment_subcategory", "diagnosis_category", "diagnosis_subcategory", "type", "imr_type"]
EXCLUDED = {
    "findings": "post-decision text that states the conclusion -> target leakage",
    "days_to_adopt": "happens after the decision -> leakage",
    "age_range": "sensitive attribute; used only for fairness slices",
    "patient_gender": "sensitive attribute; used only for fairness slices",
}


def prep(df: pd.DataFrame) -> pd.DataFrame:
    X = df[CATS].fillna("Unknown").astype(str).copy()
    X["year"] = df.year.astype(float)
    return X


def logreg() -> Pipeline:
    return Pipeline(
        [
            ("ct", ColumnTransformer([("oh", OneHotEncoder(handle_unknown="ignore", min_frequency=5), CATS), ("yr", StandardScaler(), ["year"])])),
            ("clf", LogisticRegression(C=0.5, max_iter=3000, random_state=SEED)),
        ]
    )


def hgb() -> Pipeline:
    return Pipeline(
        [
            ("ct", ColumnTransformer([("ord", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1, encoded_missing_value=-1, min_frequency=10, max_categories=250), CATS)], remainder="passthrough")),
            (
                "clf",
                HistGradientBoostingClassifier(
                    categorical_features=list(range(len(CATS))), max_iter=300, learning_rate=0.05, max_leaf_nodes=31, l2_regularization=1.0, random_state=SEED
                ),
            ),
        ]
    )


class EBBaseline:
    """Empirical-Bayes smoothed overturn rate per treatment subcategory (beta-binomial prior)."""

    def fit(self, df: pd.DataFrame) -> EBBaseline:
        g = df.groupby("treatment_subcategory").overturned.agg(["sum", "count"])
        self.alpha, self.beta = fit_beta_prior(g["sum"].astype(int).tolist(), g["count"].astype(int).tolist())
        self.rates = {k: smoothed_rate(int(r["sum"]), int(r["count"]), self.alpha, self.beta) for k, r in g.iterrows()}
        self.prior = self.alpha / (self.alpha + self.beta)
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return df.treatment_subcategory.map(lambda k: self.rates.get(k, self.prior)).astype(float).values


def _m(y, p) -> dict:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return {"roc_auc": float(roc_auc_score(y, p)) if len(set(y)) > 1 else None, "brier": float(brier_score_loss(y, p)), "log_loss": float(log_loss(y, p, labels=[0, 1]))}


def calibration_table(y, p, bins=10) -> list[dict]:
    edges = np.linspace(0, 1, bins + 1)
    out = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        m = (p > lo) & (p <= hi)
        if m.sum() >= 20:
            out.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": int(m.sum()), "mean_pred": float(p[m].mean()), "observed": float(y[m].mean())})
    return out


def fairness(df: pd.DataFrame, p: np.ndarray, col: str) -> list[dict]:
    y = df.overturned.astype(int).values
    out = []
    for g in sorted(df[col].fillna("Unknown").unique()):
        m = (df[col].fillna("Unknown") == g).values
        if m.sum() < 50:
            continue
        pred = p[m] >= 0.5
        yy = y[m]
        fpr = float(((pred == 1) & (yy == 0)).sum() / max(1, (yy == 0).sum()))
        fnr = float(((pred == 0) & (yy == 1)).sum() / max(1, (yy == 1).sum()))
        out.append({"group": g, "n": int(m.sum()), "observed_rate": float(yy.mean()), "mean_predicted": float(p[m].mean()), "calibration_gap": float(p[m].mean() - yy.mean()), "brier": float(brier_score_loss(yy, p[m])), "fpr@0.5": fpr, "fnr@0.5": fnr})
    return out


class M3Model:
    def __init__(self, pipe, beats_baseline: bool, eb: EBBaseline):
        self.pipe = pipe
        self.beats_baseline = beats_baseline
        self.eb = eb

    def estimate(self, tc, tsc, dc, imr_type_str, year: int = 2025) -> tuple[float, bool]:
        X = pd.DataFrame([{"treatment_category": tc or "Unknown", "treatment_subcategory": tsc or "Unknown", "diagnosis_category": dc or "Unknown", "diagnosis_subcategory": "Unknown", "type": imr_type_str or "Medical Necessity", "imr_type": "Standard", "year": float(year)}])
        return float(self.pipe.predict_proba(X)[0, 1]), self.beats_baseline


def train() -> dict:
    df = pd.read_parquet(DATA)
    tr, va, te, split = time_split(df)
    ytr, yva, yte = (d.overturned.astype(int).values for d in (tr, va, te))
    out: dict = {"split": split, "features": CATS + ["year"], "excluded_features": EXCLUDED, "sizes": {"train": len(tr), "validation": len(va), "test": len(te)}}
    overall = float(ytr.mean())
    out["baseline_overall_rate"] = {"validation": _m(yva, np.full(len(va), overall)), "test": _m(yte, np.full(len(te), overall))}
    eb = EBBaseline().fit(tr)
    out["baseline_eb_smoothed_subcategory"] = {"validation": _m(yva, eb.predict(va)), "test": _m(yte, eb.predict(te)), "prior_alpha": eb.alpha, "prior_beta": eb.beta}
    models = {"logreg_onehot": logreg(), "hist_gradient_boosting": hgb()}
    preds = {}
    for name, pipe in models.items():
        pipe.fit(prep(tr), ytr)
        pv, pt = pipe.predict_proba(prep(va))[:, 1], pipe.predict_proba(prep(te))[:, 1]
        preds[name] = pt
        out[name] = {"validation": _m(yva, pv), "test": _m(yte, pt)}
    best = min(models, key=lambda n: out[n]["validation"]["brier"])
    out["selected_model"] = best
    pt = preds[best]
    beats = out[best]["test"]["brier"] < out["baseline_eb_smoothed_subcategory"]["test"]["brier"]
    out["beats_eb_baseline_on_test_brier"] = bool(beats)
    out["calibration_test"] = calibration_table(yte, pt)
    out["by_year_test"] = [{"year": int(y), **_m(yte[(te.year == y).values], pt[(te.year == y).values])} for y in sorted(te.year.unique())]
    # drift: score each historical year with the selected model refit on all training data
    out["fairness_slices_test"] = {"age_range": fairness(te, pt, "age_range"), "patient_gender": fairness(te, pt, "patient_gender")}
    d = artifact_dir("m3", VERSION)
    joblib.dump(M3Model(models[best], beats, eb), d / "model.joblib")
    save_json(d / "metrics.json", out)
    save_json(d / "training_config.json", {"seed": SEED, "git_sha": git_sha(), "data_hashes": {"imr.parquet": file_hash(DATA)}, "split": split})
    (d / "model_card.md").write_text(card(out), encoding="utf-8")
    return out


def card(m: dict) -> str:
    def r(name, k):
        x = m[k]["test"]
        v = m[k]["validation"]
        return f"| {name} | {v['brier']:.4f} | {x['roc_auc'] or float('nan'):.3f} | {x['brier']:.4f} | {x['log_loss']:.4f} |"

    def fr(rows):
        lines = ["| Group | N | Observed | Mean predicted | Gap | Brier | FPR@0.5 | FNR@0.5 |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for g in rows:
            lines.append(f"| {g['group']} | {g['n']} | {g['observed_rate']:.3f} | {g['mean_predicted']:.3f} | {g['calibration_gap']:+.3f} | {g['brier']:.4f} | {g['fpr@0.5']:.3f} | {g['fnr@0.5']:.3f} |")
        return "\n".join(lines)

    cal = "\n".join(f"| {c['bin']} | {c['n']} | {c['mean_pred']:.3f} | {c['observed']:.3f} |" for c in m["calibration_test"])
    years = "\n".join(f"| {y['year']} | {y['roc_auc'] or float('nan'):.3f} | {y['brier']:.4f} |" for y in m["by_year_test"])
    return f"""# Model card: M3 overturn-rate model ({VERSION})

## What it does
Estimates P(IMR overturns the plan's decision) from case attributes, to give **context only** ("cases like this were overturned about X% of the time"). It is never used to advise against appealing (hard rule 9). The stats card shows the empirical rate with a Wilson 95% interval and N; the model estimate is shown only when it beats the empirical-Bayes baseline on Brier score and N ≥ 20.

Data: California Department of Managed Health Care, Independent Medical Review determinations (CC BY).

## Features and exclusions
Features: {", ".join(m["features"])}.

Excluded and why:
{chr(10).join(f"- `{k}`: {v}" for k, v in m["excluded_features"].items())}

## Split
Time-based, same as M2: train {m["split"]["train_years"]}, validation {m["split"]["validation_year"]}, test {m["split"]["test_years"]}. Sizes: {m["sizes"]}.

## Results
| Model | Validation Brier | Test ROC-AUC | Test Brier | Test log loss |
|---|---:|---:|---:|---:|
{r("Baseline: overall training rate", "baseline_overall_rate")}
{r("Baseline: empirical-Bayes smoothed rate per treatment subcategory", "baseline_eb_smoothed_subcategory")}
{r("Logistic regression (one-hot)", "logreg_onehot")}
{r("HistGradientBoosting (native categorical)", "hist_gradient_boosting")}

Selected by validation Brier: **{m["selected_model"]}**. Beats the EB baseline on test Brier: **{m["beats_eb_baseline_on_test_brier"]}**.

The EB baseline shrinks each subcategory's rate toward the overall rate with a beta prior fitted by method of moments; small subcategories borrow strength from the whole dataset, which makes it a strong baseline.

## Calibration (test)
| Bin | N | Mean predicted | Observed |
|---|---:|---:|---:|
{cal}

## Performance by year (drift)
| Year | ROC-AUC | Brier |
|---|---:|---:|
{years}

## Fairness slices (test; age and gender are NOT model inputs)
### Age range
{fr(m["fairness_slices_test"]["age_range"])}

### Gender
{fr(m["fairness_slices_test"]["patient_gender"])}

Read the calibration gap per group: a positive gap means the model over-predicts overturns for that group. Because age and gender are excluded as features, any gap comes through correlated features (treatment and diagnosis mix differs by age). This is measured, not corrected; Phase B should review it before the estimate is shown to users.

## Limitations
- California, managed-care (DMHC) plans only; other states and plan types differ.
- Outcome base rates shift over time (see by-year table); retrain monthly.
- Context only; never advice.
"""
