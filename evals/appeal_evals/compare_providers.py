"""Offline-vs-local-LLM comparison (SPEC 21.4).

Runs the intake-level suites (extraction, classification, deadlines) on the gold letters once per provider,
each in its own process so settings do not leak, and writes evals/reports/provider_comparison.md.

    uv run python -m appeal_evals.compare_providers            # offline + ollama, all gold letters
    uv run python -m appeal_evals.compare_providers --limit 40 # quicker: every 5th letter

Needs a running Ollama server with the model in OLLAMA_MODEL (default llama3.2:3b). The LLM only fills
extraction fields (see appeal_core/llm/ollama.py); the leak gate still runs before every call.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "evals" / "reports" / "provider_comparison.md"


def _one(limit: int | None) -> dict:
    from appeal_evals.run import jl, run_intake, suite_classification, suite_deadlines, suite_extraction

    gold = jl("letters.jsonl")
    if limit:
        step = max(1, len(gold) // limit)
        gold = gold[::step][:limit]
    t0 = time.time()
    runs = run_intake(gold)
    secs = (time.time() - t0) / max(1, len(gold))
    ex, cl, dl = suite_extraction(runs), suite_classification(runs), suite_deadlines(runs)
    return {
        "n": len(gold),
        "sec_per_letter": round(secs, 2),
        "extraction_mean": ex.metrics["mean"],
        "extraction_by_family": ex.metrics["by_family"],
        "per_field": ex.metrics["per_field"],
        "macro_f1": cl.metrics["macro_f1"],
        "ask_user_rate": cl.metrics["ask_user_rate"],
        "deadlines_exact": dl.metrics["exact"],
    }


def _run_provider(provider: str, limit: int | None) -> dict:
    env = {**os.environ, "LLM_PROVIDER": provider}
    cmd = [sys.executable, "-m", "appeal_evals.compare_providers", "--child"] + (["--limit", str(limit)] if limit else [])
    out = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=ROOT)
    line = next((ln for ln in reversed(out.stdout.splitlines()) if ln.startswith("{")), None)
    if out.returncode != 0 or line is None:
        return {"error": (out.stderr or out.stdout)[-600:]}
    return json.loads(line)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--child", action="store_true")
    a = ap.parse_args()
    if a.child:
        print(json.dumps(_one(a.limit)))
        return
    model = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
    res = {"offline": _run_provider("offline", a.limit), f"ollama ({model})": _run_provider("ollama", a.limit)}
    fields = next((r["per_field"] for r in res.values() if "per_field" in r), {})
    lines = [
        "# Offline vs local LLM (SPEC 21.4)",
        "",
        "Intake-level suites on the gold letters. The LLM fills extraction fields; classification uses the extracted",
        "reason/codes with the same M1 model, so differences there come from extraction. Letters are synthetic.",
        "",
        "| Metric | " + " | ".join(res) + " |",
        "|---|" + "---:|" * len(res),
    ]

    def row(label: str, fn) -> None:
        lines.append(f"| {label} | " + " | ".join("error" if "error" in r else fn(r) for r in res.values()) + " |")

    row("letters", lambda r: str(r["n"]))
    row("extraction, mean field accuracy", lambda r: f"{r['extraction_mean']:.3f}")
    row("extraction, notice layout (gold)", lambda r: f"{r['extraction_by_family'].get('gold', float('nan')):.3f}")
    row("extraction, EOB layout", lambda r: f"{r['extraction_by_family'].get('eob', float('nan')):.3f}")
    for f in fields:
        row(f"  {f}", lambda r, f=f: f"{r['per_field'][f]:.3f}")
    row("classification macro-F1", lambda r: f"{r['macro_f1']:.3f}")
    row("ask-user rate", lambda r: f"{r['ask_user_rate']:.3f}")
    row("deadlines exact", lambda r: f"{r['deadlines_exact']:.3f}")
    row("seconds per letter (CPU)", lambda r: f"{r['sec_per_letter']:.2f}")
    errs = {k: v["error"] for k, v in res.items() if "error" in v}
    if errs:
        lines += ["", "Errors:", ""] + [f"- {k}: `{v.strip().splitlines()[-1] if v.strip() else v}`" for k, v in errs.items()]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
