"""`make evaluate-models` -> ml/reports/latest.md comparing pinned versions with the recorded baseline."""

from __future__ import annotations

import json

from appeal_ml.common import ARTIFACTS, REPORTS, pinned
from appeal_ml.promotion_check import BASELINE, primary_value


def write_report() -> str:
    REPORTS.mkdir(parents=True, exist_ok=True)
    base = json.loads(BASELINE.read_text()) if BASELINE.exists() else {}
    lines = ["# ML report (latest)", "", "| Model | Version | Primary metric | Value | Previous (baseline) |", "|---|---|---|---:|---:|"]
    names = {"m1": "gold macro-F1", "m2": "test macro-F1 (shortcuts removed)", "m3": "test Brier (selected model)"}
    details = []
    for model, version in sorted(pinned().items()):
        p = ARTIFACTS / model / version / "metrics.json"
        if not p.exists():
            continue
        m = json.loads(p.read_text())
        v = primary_value(model, m)
        lines.append(f"| {model} | {version} | {names[model]} | {v:.4f} | {base.get(model, float('nan')):.4f} |")
        details.append((model, m))
    for model, m in details:
        lines += ["", f"## {model}", ""]
        if model == "m1":
            lines += [
                f"- Selected: {m['selected_model']}; validation macro-F1 {m['validation_macro_f1']}",
                f"- Gold macro-F1 {m['gold_macro_f1']:.3f}; ECE OOF {m['oof_ece_calibrated']:.4f}, gold {m['gold_ece']:.4f}",
                f"- Ask-user threshold {m['ask_user_threshold']:.2f}; gold coverage {m['gold_coverage_at_threshold']:.1%}, accuracy when answered {m['gold_accuracy_when_answered']}",
                f"- Ablation without codes: gold macro-F1 {m['ablation_no_codes']['gold_macro_f1']:.3f}",
            ]
        if model == "m2":
            for k in ("tfidf_lr", "tfidf_lr_shortcuts_removed", "embeddings_lr"):
                r = m.get(k, {})
                if "test" in r:
                    lines.append(f"- {k}: validation {r['validation']['macro_f1']:.3f}, test {r['test']['macro_f1']:.3f}")
            lines.append(f"- Majority baseline test macro-F1 {m['baseline_majority']['macro_f1']:.3f}; split {m['split']}")
        if model == "m3":
            for k in ("baseline_overall_rate", "baseline_eb_smoothed_subcategory", "logreg_onehot", "hist_gradient_boosting"):
                t = m[k]["test"]
                lines.append(f"- {k}: test ROC-AUC {t['roc_auc'] or float('nan'):.3f}, Brier {t['brier']:.4f}, log loss {t['log_loss']:.4f}")
            lines.append(f"- Selected {m['selected_model']}; beats EB baseline on Brier: {m['beats_eb_baseline_on_test_brier']}")
    lines += ["", "Model cards: `ml/artifacts/<model>/<version>/model_card.md`."]
    text = "\n".join(lines) + "\n"
    (REPORTS / "latest.md").write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    print(write_report())
