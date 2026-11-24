"""DSPy optimization of the extraction prompt (P1): hand-written prompt vs DSPy-optimized program.

    uv run python -m appeal_evals.dspy_extract [--train 40] [--test 60]

- Hand-written: the production `intake_extract` prompt (LangChain structured output, cheap tier).
- DSPy: a `dspy.Predict` signature with the same fields, optimized with BootstrapFewShotWithRandomSearch on
  synthetic TRAINING letters (labels from the generator), scored by exact field accuracy.
- Both are evaluated on the same evenly spaced sample of gold letters (never used for optimization).

DSPy calls OpenAI through LiteLLM, and the gateway's callback prices them into ledger session `dspy`
(hard cap DSPY_BUDGET_USD, default $2). Only tokenized letters are sent.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path

os.environ.setdefault("LLM_SESSION", "dspy")
os.environ.setdefault("LLM_BUDGET_USD", os.environ.get("DSPY_BUDGET_USD", "2"))
os.environ["LLM_PROVIDER"] = "openai"

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "evals" / "reports" / "dspy_extraction.md"
FIELDS = ["insurer", "plan_type", "state", "service", "date_of_service", "notice_date", "denial_reason", "denial_codes"]


def _jl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def _truth(g: dict) -> dict:
    f = g["label"]["fields"]
    return {**{k: f.get(k) for k in FIELDS}, "denial_reason": g["label"]["reason_text"]}


def _ok(got, exp, f: str) -> bool:
    if f == "denial_codes":
        return sorted(got or []) == sorted(exp or [])
    return (str(got or "")).strip().lower() == (str(exp or "")).strip().lower()


def _acc(pred: dict, exp: dict) -> float:
    return statistics.mean(_ok(pred.get(f), exp.get(f), f) for f in FIELDS)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", type=int, default=40)
    ap.add_argument("--test", type=int, default=60)
    a = ap.parse_args()

    import dspy
    from appeal_core.llm.cost import get_ledger
    from appeal_core.llm.gateway import router
    from appeal_core.settings import get_settings

    from appeal_evals.finetune import _tokenize

    router()  # installs the gateway's pricing callback and per-process budget for DSPy's LiteLLM calls
    s = get_settings()
    lm = dspy.LM(f"openai/{s.openai_model_fast}", api_key=s.openai_api_key, temperature=0, cache=False, store=False)
    dspy.configure(lm=lm)

    class ExtractDenial(dspy.Signature):
        """Extract facts from a health insurance denial letter. Identifiers are tokens like [MEMBER_ID_1]; copy
        insurer, service and denial_reason word for word; dates YYYY-MM-DD; empty string when not stated."""

        letter: str = dspy.InputField()
        insurer: str = dspy.OutputField()
        plan_type: str = dspy.OutputField(desc="employer_self_funded | employer_fully_insured | individual_marketplace | medicare_advantage | medicaid_managed_care")
        state: str = dspy.OutputField(desc="two-letter code")
        service: str = dspy.OutputField()
        date_of_service: str = dspy.OutputField()
        notice_date: str = dspy.OutputField()
        denial_reason: str = dspy.OutputField(desc="the reason sentence, copied exactly")
        denial_codes: list[str] = dspy.OutputField()

    train_rows = _jl(ROOT / "data" / "processed" / "letters" / "train.jsonl")
    train_rows = train_rows[:: max(1, len(train_rows) // a.train)][: a.train]
    gold = _jl(ROOT / "evals" / "gold" / "letters.jsonl")
    gold = gold[:: max(1, len(gold) // a.test)][: a.test]

    def ex(g: dict) -> dspy.Example:
        tok, _ = _tokenize(g["text"])
        return dspy.Example(letter=tok, **_truth(g)).with_inputs("letter")

    trainset = [ex(g) for g in train_rows]
    testset = [ex(g) for g in gold]

    def metric(example, pred, trace=None) -> float:
        return _acc({f: getattr(pred, f, None) for f in FIELDS}, {f: example[f] for f in FIELDS})

    baseline = dspy.Predict(ExtractDenial)
    t0 = time.time()
    opt = dspy.BootstrapFewShotWithRandomSearch(metric=metric, max_bootstrapped_demos=3, max_labeled_demos=3, num_candidate_programs=4, num_threads=4)
    optimized = opt.compile(baseline, trainset=trainset)
    opt_secs = time.time() - t0

    def score_dspy(prog) -> float:
        return statistics.mean(metric(e, prog(letter=e.letter)) for e in testset)

    # the production prompt, through the same LangChain chain the app uses
    from appeal_core.adapters import get_llm

    llm = get_llm()

    def score_hand() -> float:
        vals = []
        for e in testset:
            out = llm.extract(e.letter, [])
            vals.append(_acc({k: v["value"] for k, v in out["fields"].items()}, {f: e[f] for f in FIELDS}))
        return statistics.mean(vals)

    results = {
        "hand-written prompt (production intake_extract 2.0.0, LangChain structured output + grounding merge)": score_hand(),
        "DSPy Predict, zero-shot (same fields, no optimization)": score_dspy(baseline),
        "DSPy Predict, optimized (BootstrapFewShotWithRandomSearch, 3 demos)": score_dspy(optimized),
    }
    optimized.save(str(ROOT / "var" / "dspy_extract_optimized.json"))
    led = get_ledger().summary()
    lines = [
        "# DSPy: hand-written vs optimized extraction prompt",
        "",
        f"Cheap tier `{s.openai_model_fast}`. Optimized on {len(trainset)} synthetic training letters; scored on {len(testset)} gold letters "
        f"(mean exact-match accuracy over {len(FIELDS)} fields). Optimization took {opt_secs:.0f} s. Spend: ${led['usd']:.3f} (session `{led['session']}`).",
        "",
        "| Program | Gold field accuracy |",
        "|---|---:|",
        *[f"| {k} | {v:.3f} |" for k, v in results.items()],
        "",
        "The production path also merges model answers over the deterministic extractor and rejects quotes that are not in the "
        "letter, which DSPy's programs do not do; the comparison shows what prompt optimization alone buys.",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
