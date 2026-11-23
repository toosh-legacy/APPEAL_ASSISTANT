"""Promotion rule: a new version is pinned only if it does not regress the primary metric by > 1 point
versus the previously recorded metrics (ml/reports/baseline_metrics.json). CI runs this as a check."""

from __future__ import annotations

import json
import sys

from appeal_ml.common import ARTIFACTS, REPORTS, pinned, save_json

PRIMARY = {
    "m1": ("gold_macro_f1", "higher"),
    "m2": ("tfidf_lr_shortcuts_removed.test.macro_f1", "higher"),
    "m3": ("{selected}.test.brier", "lower"),
}
BASELINE = REPORTS / "baseline_metrics.json"


def primary_value(model: str, metrics: dict) -> float:
    key, _ = PRIMARY[model]
    key = key.replace("{selected}", metrics.get("selected_model", ""))
    v = metrics
    for part in key.split("."):
        v = v[part]
    return float(v)


def baseline_key(model: str) -> str:
    """Baselines are only comparable on the same data: M2/M3 key on the IMR source (real vs CI synthetic sample)."""
    if model == "m1":
        return model
    try:
        from appeal_ml.common import ROOT

        src = json.loads((ROOT / "data" / "manifest.json").read_text())["datasets"]["imr"]["source"]
    except Exception:
        src = "unknown"
    return model if src == "real" else f"{model}@{src}"


def should_promote(model: str, version: str) -> tuple[bool, str]:
    m = json.loads((ARTIFACTS / model / version / "metrics.json").read_text())
    new = primary_value(model, m)
    base = json.loads(BASELINE.read_text()) if BASELINE.exists() else {}
    key = baseline_key(model)
    if key not in base:
        base[key] = new
        REPORTS.mkdir(parents=True, exist_ok=True)
        save_json(BASELINE, base)
        return True, f"first version, primary={new:.4f}"
    old = base[key]
    direction = PRIMARY[model][1]
    regress = (old - new) if direction == "higher" else (new - old)
    tol = 0.01 if model != "m3" else 0.001  # 1 point (F1) / 0.001 Brier
    if regress > tol:
        return False, f"primary regressed {old:.4f} -> {new:.4f}"
    return True, f"primary {old:.4f} -> {new:.4f}"


def main() -> int:
    bad = []
    for model, version in pinned().items():
        p = ARTIFACTS / model / version / "metrics.json"
        if not p.exists():
            continue
        ok, why = should_promote(model, version)
        print(f"{model}@{version}: {why}")
        if not ok:
            bad.append(model)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
