# Evaluation report (latest)

Mode: full · git 0f38ac3fe7 · LLM provider: offline · prompts {'intake_extract': '1.0.0', 'query_rewrite': '1.0.0', 'writer_letter': '1.0.0'} · models {'m1': 'v1', 'm2': 'v1', 'm3': 'v1'}

| Suite | Gate | Result | Key metrics |
|---|---|---|---|
| extraction | every field exact match >= 0.90 | PASS | `{"per_field": {"insurer": 1.0, "plan_type": 1.0, "state": 1.0, "claim_number": 1.0, "member_id": 1.0, "service": 1.0, "date_of_service": 1.0, "notice_date": 1.0, "denial_codes": 1.0}, "mean": 1.0, "n": 120}` |
| classification | macro-F1 >= 0.80 | PASS | `{"macro_f1": 0.838, "per_class_recall": {"medical_necessity": 1.0, "prior_authorization": 0.6, "out_of_network": 1.0, "coding_billing_error": 0.8, "experimental_investigational": 1.0, "not_covered_benefit": 1.0, "timely_filing": 0.733, "other_unclear": 0.533}, "ask_user_rate": 0.175, "sources": {"model": 55, "denial_code": 65}}` |
| deadlines | exact due date 100% | PASS | `{"exact": 1.0}` |
| retrieval | recall@5 >= 0.85 (hybrid RRF + rewriting) | FAIL | `{"production": {"recall@5": 0.8043, "mrr": 0.8188, "ndcg@10": 0.7679}}` |
| citation_validity | 100% of cited IDs exist in the case's retrieval set | PASS | `{"citations": 456, "invalid": 0, "validity": 1.0}` |
| support | deterministic checker marks >= 95% of cited sentences supported | PASS | `{"cited_sentences": 456, "supported": 456, "rate": 1.0}` |
| precedent_wording | 100% of P-citing sentences use non-binding wording | PASS | `{"precedent_sentences": 143, "non_binding": 143, "letters_citing_precedents": 99}` |
| red_team | 0 injection cases change behavior or leak data | PASS | `{"cases": 40, "failures": 0, "detected_by_heuristics": 36, "outbound_tools": 0}` |
| privacy | 0 raw identifiers in captured provider inputs | PASS | `{"payloads_checked": 621, "raw_identifier_hits": 0, "leak_gate_blocks": 0, "cases": 190}` |
| budget | p50 seconds per case <= 10 (offline providers) | PASS | `{"p50_s": 0.738, "p95_s": 0.95, "n": 120, "statuses": {"READY": 120}}` |

## Failing: retrieval

```
{
 "production": {
  "recall@5": 0.8043,
  "mrr": 0.8188,
  "ndcg@10": 0.7679
 },
 "ablation": {
  "keyword only": {
   "recall@5": 0.5957,
   "mrr": 0.7116,
   "ndcg@10": 0.6384
  },
  "vector only": {
   "recall@5": 0.6722,
   "mrr": 0.776,
   "ndcg@10": 0.706
  },
  "hybrid RRF": {
   "recall@5": 0.7742,
   "mrr": 0.8076,
   "ndcg@10": 0.7632
  },
  "hybrid RRF + query rewriting": {
   "recall@5": 0.8043,
   "mrr": 0.8188,
   "ndcg@10": 0.7679
  }
 }
}
```

## Retrieval ablation

See `evals/reports/retrieval_ablation.md`.
