"""Retrieval evaluation (SPEC 11.5): recall@5, MRR, nDCG@10 on the gold questions + ablation table."""

from __future__ import annotations

import json
import math
from pathlib import Path

from appeal_core.llm.offline import offline_rewrite
from appeal_core.retrieval.retriever import HybridRetriever

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "evals" / "gold" / "retrieval.jsonl"
REPORTS = ROOT / "evals" / "reports"


def load_gold() -> list[dict]:
    return [json.loads(line) for line in GOLD.read_text(encoding="utf-8").splitlines() if line.strip()]


def metrics_for(ranked: list[str], relevant: set[str]) -> dict[str, float]:
    top5 = ranked[:5]
    hits5 = len([d for d in top5 if d in relevant])
    recall5 = hits5 / min(len(relevant), 5)
    rr = 0.0
    for i, d in enumerate(ranked, start=1):
        if d in relevant:
            rr = 1.0 / i
            break
    dcg = sum(1.0 / math.log2(i + 1) for i, d in enumerate(ranked[:10], start=1) if d in relevant)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(relevant), 10) + 1))
    return {"recall@5": recall5, "mrr": rr, "ndcg@10": dcg / idcg if idcg else 0.0}


def run_config(retr: HybridRetriever, gold: list[dict], mode: str, rewrite: bool, diversify: bool = False) -> tuple[dict, list[dict]]:
    per = []
    for g in gold:
        queries = offline_rewrite(g["query"]) if rewrite else [g["query"]]
        if g["collection"] == "rules":
            res = retr.search_rules(queries, plan_type=g.get("plan_type"), k=10, mode=mode, diversify=diversify)
            ranked = [r["id"] for r in res]
        else:
            res = retr.search_precedents(queries, k=10, mode=mode, diversify=diversify)
            ranked = [r["id"] for r in res]
        m = metrics_for(ranked, set(g["relevant"]))
        per.append({"id": g["id"], "collection": g["collection"], "query": g["query"], **m, "top5": ranked[:5]})
    agg = {}
    for coll in ("all", "rules", "precedents"):
        rows = [p for p in per if coll == "all" or p["collection"] == coll]
        agg[coll] = {k: round(sum(r[k] for r in rows) / max(1, len(rows)), 4) for k in ("recall@5", "mrr", "ndcg@10")}
    return agg, per


PRODUCTION = "hybrid RRF + rewriting + diversification (production)"
CONFIGS = [
    ("keyword only", "keyword", False, False),
    ("vector only", "vector", False, False),
    ("hybrid RRF", "hybrid", False, False),
    ("hybrid RRF + query rewriting", "hybrid", True, False),
    (PRODUCTION, "hybrid", True, True),
]


def ablation(url: str | None = None, write: bool = True) -> dict:
    gold = load_gold()
    retr = HybridRetriever(url=url)
    results = {}
    per_best = None
    for name, mode, rw, div in CONFIGS:
        agg, per = run_config(retr, gold, mode, rw, div)
        results[name] = agg
        if name == PRODUCTION:
            per_best = per
    if write:
        REPORTS.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Retrieval ablation (SPEC 11.5)",
            "",
            f"Gold set: {len(gold)} questions ({sum(g['collection'] == 'rules' for g in gold)} regulations/summaries, "
            f"{sum(g['collection'] == 'precedents' for g in gold)} precedents). Relevance labels come from text/metadata filters, not from the retriever "
            "(see `evals/appeal_evals/build_retrieval_gold.py`). recall@5 is normalized by min(|relevant|, 5).",
            "",
            "| Configuration | recall@5 (all) | MRR (all) | nDCG@10 (all) | recall@5 rules | recall@5 precedents |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for name, agg in results.items():
            lines.append(f"| {name} | {agg['all']['recall@5']:.3f} | {agg['all']['mrr']:.3f} | {agg['all']['ndcg@10']:.3f} | {agg['rules']['recall@5']:.3f} | {agg['precedents']['recall@5']:.3f} |")
        lines += [
            "",
            "Notes:",
            "- Query rewriting: the user's query feeds both keyword and vector search (weight 1.0); "
            "dictionary rewrites feed only the vector side (weight 0.25). Rewrites on the keyword side hurt (OR-queries with many legal terms match everything).",
            "- Production adds SPEC 11.3 step 5 diversification (at least one procedural-rights chunk and one rights summary; both outcomes and "
            "same-subcategory/recent cases for precedents). It raises recall@5 but lowers MRR, because forced items can take the top slots.",
            "- The rewrite dictionary and RRF weights were adjusted after inspecting misses on this gold set, so these numbers are optimistic; "
            "Phase B should add held-out questions written by a person.",
            "- Precedent questions are answered without metadata filters here; in the product, Research also filters by the treatment category inferred from the service.",
        ]
        lines += ["", "Phase C will add a fifth row: Azure AI Search hybrid + semantic ranker.", "", "## Misses (production config, recall@5 < 1)", ""]
        for p in per_best or []:
            if p["recall@5"] < 1:
                lines.append(f"- `{p['id']}` {p['query']} — recall@5 {p['recall@5']:.2f}, MRR {p['mrr']:.2f}")
        (REPORTS / "retrieval_ablation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (REPORTS / "retrieval_per_question.json").write_text(json.dumps(per_best, indent=1), encoding="utf-8")
    return results


if __name__ == "__main__":
    print(json.dumps(ablation(), indent=1))
