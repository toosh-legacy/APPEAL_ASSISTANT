# Evaluation report (latest)

Mode: live (OpenAI via LiteLLM) · git 668ab443eb · LLM provider: openai via LiteLLM (fast gpt-4.1-mini, strong gpt-4.1, embeddings text-embedding-3-small) · prompts {'classifier_category': '1.0.0', 'intake_extract': '2.0.0', 'query_rewrite': '2.0.0', 'reviewer_letter': '1.0.0', 'writer_letter': '2.0.0'} · models {'m1': 'v1', 'm2': 'v1', 'm3': 'v1'}

| Suite | Gate | Result | Key metrics |
|---|---|---|---|
| extraction | every field exact match >= 0.90 | PASS | `{"per_field": {"insurer": 1.0, "plan_type": 1.0, "state": 1.0, "claim_number": 1.0, "member_id": 1.0, "service": 1.0, "date_of_service": 1.0, "notice_date": 1.0, "denial_reason": 0.975, "denial_codes": 1.0}, "mean": 0.9975, "n": 40, "by_family": {"gold": 1.0, "eob": 0.9938}}` |
| classification | macro-F1 >= 0.80 | FAIL | `{"macro_f1": 0.7981, "per_class_recall": {"medical_necessity": 1.0, "prior_authorization": 0.2, "out_of_network": 1.0, "coding_billing_error": 1.0, "experimental_investigational": 1.0, "not_covered_benefit": 1.0, "timely_filing": 1.0, "other_unclear": 0.4}, "ask_user_rate": 0.0, "sources": {"llm": 9, "denial_code": 14, "model": 17}}` |
| deadlines | exact due date 100% | PASS | `{"exact": 1.0}` |
| retrieval | recall@5 >= 0.85 (production retrieval path) | PASS | `{"production": {"recall@5": 0.8545, "mrr": 0.9009, "ndcg@10": 0.863}, "heldout_recall@5": 0.7065, "sealed_recall@5": 0.7553, "reranker": "crossencoder"}` |
| citation_validity | 100% of cited IDs exist in the case's retrieval set | PASS | `{"citations": 176, "invalid": 0, "validity": 1.0}` |
| support | deterministic checker marks >= 95% of cited sentences supported | PASS | `{"cited_sentences": 174, "supported": 169, "rate": 0.9713}` |
| precedent_wording | 100% of P-citing sentences use non-binding wording | PASS | `{"precedent_sentences": 55, "non_binding": 55, "letters_citing_precedents": 40}` |
| red_team | 0 injection cases change behavior or leak data | PASS | `{"cases": 10, "failures": 0, "detected_by_heuristics": 10, "outbound_tools": 0}` |
| privacy | 0 raw identifiers in captured provider inputs | PASS | `{"payloads_checked": 455, "raw_identifier_hits": 0, "leak_gate_blocks": 0, "cases": 60}` |
| budget | p50 seconds per case <= 30 (hosted models) | PASS | `{"p50_s": 23.14, "p95_s": 25.887, "n": 40, "statuses": {"READY": 9, "NEEDS_HUMAN": 31}}` |
| llm_cost | cost per case <= $0.10; session spend under its hard cap | PASS | `{"usd_total": 4.9553, "usd_per_case": 0.08259, "usd_per_1000_cases": 82.59, "calls": 886, "tokens_in": 2349852, "tokens_out": 178089, "cache_lookups": 1036, "cache_hits": 876, "cache_hit_rate": 0.8456, "usd_saved_by_cache": 0.00905, "session": "eval-live-1", "budget_usd": 5.0}` |
| ragas | faithfulness >= 0.80 (reported: answer relevancy, context precision, context recall) | FAIL (non-blocking) | `{"n": 15, "faithfulness": 0.3887, "answer_relevancy": 0.7093, "llm_context_precision_with_reference": 0.6714, "context_recall": 0.9233}` |

## Failing: classification

```
{
 "macro_f1": 0.7981,
 "per_class_recall": {
  "medical_necessity": 1.0,
  "prior_authorization": 0.2,
  "out_of_network": 1.0,
  "coding_billing_error": 1.0,
  "experimental_investigational": 1.0,
  "not_covered_benefit": 1.0,
  "timely_filing": 1.0,
  "other_unclear": 0.4
 },
 "ask_user_rate": 0.0,
 "sources": {
  "llm": 9,
  "denial_code": 14,
  "model": 17
 }
}
```

## Failing: ragas

```
{
 "n": 15,
 "faithfulness": 0.3887,
 "answer_relevancy": 0.7093,
 "llm_context_precision_with_reference": 0.6714,
 "context_recall": 0.9233
}
```

## Retrieval ablation

See `evals/reports/retrieval_ablation.md`.
