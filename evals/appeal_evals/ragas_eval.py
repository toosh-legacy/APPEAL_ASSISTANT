"""Ragas RAG evaluation of finished letters (live runs only: the judge is the strong-tier model).

Per READY case:
- user_input: the appeal task (category, service, denial reason)
- retrieved_contexts: what Research retrieved through the LangChain retrievers (rules + precedents)
- response: the retrieval-grounded sections (grounds + precedents); the rest of the letter restates the member's
  own facts, which are not retrieved contexts and would count as unfaithful by construction
- reference: the KB playbook's legal arguments for the category (written from the regulations, reviewed
  separately), standing in for a hand-written ideal answer

Metrics: faithfulness, answer (response) relevancy, context precision (with reference), context recall.
Judge LLM and embeddings both go through the LiteLLM gateway (priced, budget-capped).
"""

from __future__ import annotations

from typing import Any

from appeal_core.kb import playbooks
from appeal_core.privacy.pii import regex_detect

METRIC_NAMES = ["faithfulness", "answer_relevancy", "llm_context_precision_with_reference", "context_recall"]


def samples_from(runs: list[dict], limit: int = 15) -> list[dict[str, Any]]:
    out = []
    for r in runs:
        if r["status"] not in ("READY", "NEEDS_HUMAN") or not r.get("sections") or not r.get("research"):
            continue
        res, f = r["research"], r["g"]["label"]["fields"]
        # the retrieval-grounded part of the letter; facts/requests come from the member, not from the contexts
        body = " ".join(s["text"] for sec in r["sections"] if sec["id"] in ("grounds", "precedents") for s in sec["sentences"])
        if not body:
            continue
        contexts = [x["text"] for x in res.get("rules", [])] + [x["excerpt"] for x in res.get("precedents", [])]
        pb = playbooks()[r["category"]]
        sample = {
            "user_input": f"Write an appeal letter for a {r['category'].replace('_', ' ')} denial of {f.get('service')}. Denial reason: {r['g']['label']['reason_text']}",
            "retrieved_contexts": contexts,
            "response": body,
            "reference": " ".join(a["text"] for a in pb.get("legal", [])),
        }
        if regex_detect(body):  # identifiers must already be tokens; never send a letter that still has one
            continue
        out.append(sample)
        if len(out) >= limit:
            break
    return out


def evaluate_runs(runs: list[dict], limit: int = 15) -> dict[str, Any]:
    from appeal_core.llm.gateway import GatewayEmbeddings, get_chat
    from ragas import EvaluationDataset, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics._answer_relevance import ResponseRelevancy
    from ragas.metrics._context_precision import LLMContextPrecisionWithReference
    from ragas.metrics._context_recall import LLMContextRecall
    from ragas.metrics._faithfulness import Faithfulness
    from ragas.run_config import RunConfig

    samples = samples_from(runs, limit)
    if not samples:
        return {"n": 0}
    llm = LangchainLLMWrapper(get_chat("strong"))
    emb = LangchainEmbeddingsWrapper(GatewayEmbeddings())
    metrics = [Faithfulness(), ResponseRelevancy(strictness=1), LLMContextPrecisionWithReference(), LLMContextRecall()]
    res = evaluate(
        EvaluationDataset.from_list(samples), metrics=metrics, llm=llm, embeddings=emb, run_config=RunConfig(max_workers=4, timeout=120), show_progress=False
    )
    df = res.to_pandas()
    means = {m: round(float(df[m].mean()), 4) for m in METRIC_NAMES if m in df}
    return {"n": len(samples), **means}
