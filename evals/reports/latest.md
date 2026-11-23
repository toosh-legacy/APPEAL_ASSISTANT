# Evaluation report (latest)

Mode: full · git d70b128536 · LLM provider: offline · prompts {'intake_extract': '1.0.0', 'query_rewrite': '1.0.0', 'writer_letter': '1.0.0'} · models {'m1': 'v1', 'm2': 'v1', 'm3': 'v1'}

| Suite | Gate | Result | Key metrics |
|---|---|---|---|
| extraction | every field exact match >= 0.90 | PASS | `{"per_field": {"insurer": 1.0, "plan_type": 1.0, "state": 1.0, "claim_number": 1.0, "member_id": 1.0, "service": 1.0, "date_of_service": 1.0, "notice_date": 1.0, "denial_reason": 1.0, "denial_codes": 1.0}, "mean": 1.0, "n": 120}` |
| classification | macro-F1 >= 0.80 | PASS | `{"macro_f1": 0.838, "per_class_recall": {"medical_necessity": 1.0, "prior_authorization": 0.6, "out_of_network": 1.0, "coding_billing_error": 0.8, "experimental_investigational": 1.0, "not_covered_benefit": 1.0, "timely_filing": 0.733, "other_unclear": 0.533}, "ask_user_rate": 0.175, "sources": {"model": 55, "denial_code": 65}}` |
| deadlines | exact due date 100% | PASS | `{"exact": 1.0}` |
| retrieval | recall@5 >= 0.85 (production retrieval path) | PASS | `{"production": {"recall@5": 0.8545, "mrr": 0.9009, "ndcg@10": 0.863}, "heldout_recall@5": 0.7065, "sealed_recall@5": 0.7553, "reranker": "crossencoder"}` |
| citation_validity | 100% of cited IDs exist in the case's retrieval set | PASS | `{"citations": 476, "invalid": 0, "validity": 1.0}` |
| support | deterministic checker marks >= 95% of cited sentences supported | PASS | `{"cited_sentences": 476, "supported": 476, "rate": 1.0}` |
| precedent_wording | 100% of P-citing sentences use non-binding wording | PASS | `{"precedent_sentences": 139, "non_binding": 139, "letters_citing_precedents": 96}` |
| red_team | 0 injection cases change behavior or leak data | PASS | `{"cases": 40, "failures": 0, "detected_by_heuristics": 36, "outbound_tools": 0}` |
| privacy | 0 raw identifiers in captured provider inputs | PASS | `{"payloads_checked": 575, "raw_identifier_hits": 0, "leak_gate_blocks": 0, "cases": 190}` |
| budget | p50 seconds per case <= 10 (offline providers) | PASS | `{"p50_s": 5.303, "p95_s": 6.32, "n": 120, "statuses": {"READY": 120}}` |

## Retrieval ablation

See `evals/reports/retrieval_ablation.md`.
