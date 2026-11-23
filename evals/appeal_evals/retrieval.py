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


HELDOUT = GOLD.with_name("retrieval_heldout.jsonl")
SEALED = GOLD.with_name("retrieval_sealed.jsonl")


def load_set(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


PRODUCTION = "hybrid RRF + rewriting + diversification + cross-encoder rerank (production)"
NO_RERANK = "hybrid RRF + rewriting + diversification"
# (name, mode, rewrite, diversify, reranker)
CONFIGS = [
    ("keyword only", "keyword", False, False, "none"),
    ("vector only", "vector", False, False, "none"),
    ("hybrid RRF", "hybrid", False, False, "none"),
    ("hybrid RRF + query rewriting", "hybrid", True, False, "none"),
    (NO_RERANK, "hybrid", True, True, "none"),
    (PRODUCTION, "hybrid", True, True, "crossencoder"),
]
# Held-out sets are only run for the two production-like rows (keeps `make eval` time reasonable).
HELDOUT_ROWS = {NO_RERANK, PRODUCTION}


def ablation(url: str | None = None, write: bool = True, production_reranker: str | None = None) -> dict:
    """Returns {config: {"all"|"rules"|"precedents": metrics, "heldout": metrics|None, "sealed": metrics|None}}.

    production_reranker overrides the reranker of the production row (CI passes "none": no model download)."""
    gold, held, sealed = load_gold(), load_set(HELDOUT), load_set(SEALED)
    results: dict[str, dict] = {}
    per_best = None
    for name, mode, rw, div, rr in CONFIGS:
        if name == PRODUCTION and production_reranker:
            rr = production_reranker
        retr = HybridRetriever(url=url, reranker=rr)
        agg, per = run_config(retr, gold, mode, rw, div)
        if name in HELDOUT_ROWS:
            agg["heldout"] = run_config(retr, held, mode, rw, div)[0]["all"] if held else None
            agg["sealed"] = run_config(retr, sealed, mode, rw, div)[0]["all"] if sealed else None
        results[name] = agg
        if name == PRODUCTION:
            per_best = per
    if write:
        _write_report(results, gold, held, sealed, per_best or [])
    return results


def _fmt(m: dict | None) -> str:
    return f"{m['recall@5']:.3f}" if m else "—"


def _write_report(results: dict, gold: list[dict], held: list[dict], sealed: list[dict], per_best: list[dict]) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    n_rules = sum(g["collection"] == "rules" for g in gold)
    lines = [
        "# Retrieval ablation (SPEC 11.5)",
        "",
        f"- **Dev set** `evals/gold/retrieval.jsonl`: {len(gold)} questions ({n_rules} regulations/summaries, {len(gold) - n_rules} precedents). "
        "The rewrite dictionary and RRF weights were tuned on it, so its numbers are optimistic. The SPEC gate is measured here.",
        f"- **Held-out #1** `retrieval_heldout.jsonl`: {len(held)} questions written after the dev work, labels fixed before any run. "
        "Its failure *types* were then inspected to design the diversification fixes, so it is no longer fully unseen.",
        f"- **Sealed** `retrieval_sealed.jsonl`: {len(sealed)} questions written before those fixes and run once after the "
        "configuration was frozen. The most honest number here.",
        "- Labels come from text/metadata rules, never from the retriever (`evals/appeal_evals/build_retrieval_gold.py`). "
        "recall@5 is normalized by min(|relevant|, 5).",
        "",
        "| Configuration | dev recall@5 | dev MRR | dev nDCG@10 | dev rules | dev precedents | held-out #1 recall@5 | sealed recall@5 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, agg in results.items():
        a = agg["all"]
        lines.append(
            f"| {name} | {a['recall@5']:.3f} | {a['mrr']:.3f} | {a['ndcg@10']:.3f} | {agg['rules']['recall@5']:.3f} | "
            f"{agg['precedents']['recall@5']:.3f} | {_fmt(agg.get('heldout'))} | {_fmt(agg.get('sealed'))} |"
        )
    lines += [
        "",
        "Notes:",
        "- Query rewriting: the user's query feeds both keyword and vector search (weight 1.0); dictionary rewrites feed only the "
        "vector side (weight 0.25). Rewrites on the keyword side hurt (OR-queries with many legal terms match everything).",
        "- Diversification (SPEC 11.3 step 5): required deadline chunks first; at least one procedural-rights chunk and exactly one "
        "rights summary, kept at their natural rank; 'Definitions' sections moved back unless the question asks what something means; "
        "both outcomes and same-subcategory/recent cases for precedents.",
        "- Reranker: cross-encoder/ms-marco-MiniLM-L-6-v2 (local, CPU) reorders the top 30 fused candidates by the user's query. "
        "Top-30 was fixed before measuring, not tuned. Costs about 1 s per search on a laptop CPU.",
        "- Precedent questions are answered without metadata filters here; in the product, Research also filters by the treatment "
        "category inferred from the service.",
        "",
        "Phase C will add a row: Azure AI Search hybrid + semantic ranker.",
        "",
        "## Misses (production config, dev set, recall@5 < 1)",
        "",
    ]
    for p in per_best:
        if p["recall@5"] < 1:
            lines.append(f"- `{p['id']}` {p['query']} — recall@5 {p['recall@5']:.2f}, MRR {p['mrr']:.2f}")
    (REPORTS / "retrieval_ablation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (REPORTS / "retrieval_per_question.json").write_text(json.dumps(per_best, indent=1), encoding="utf-8")


if __name__ == "__main__":
    print(json.dumps(ablation(), indent=1))
