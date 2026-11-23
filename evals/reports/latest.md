# Evaluation report (latest)

Mode: full · git 592d132e51 · LLM provider: offline · prompts {'intake_extract': '1.0.0', 'query_rewrite': '1.0.0', 'writer_letter': '1.0.0'} · models {'m1': 'v1', 'm2': 'v1', 'm3': 'v1'}

| Suite | Gate | Result | Key metrics |
|---|---|---|---|
| extraction | every field exact match >= 0.90 | PASS | `{"per_field": {"insurer": 1.0, "plan_type": 1.0, "state": 1.0, "claim_number": 1.0, "member_id": 1.0, "service": 1.0, "date_of_service": 1.0, "notice_date": 1.0, "denial_reason": 1.0, "denial_codes": 1.0}, "mean": 1.0, "n": 200, "by_family": {"gold": 1.0, "eob": 1.0}}` |
| classification | macro-F1 >= 0.80 | PASS | `{"macro_f1": 0.8454, "per_class_recall": {"medical_necessity": 1.0, "prior_authorization": 0.6, "out_of_network": 1.0, "coding_billing_error": 0.8, "experimental_investigational": 1.0, "not_covered_benefit": 1.0, "timely_filing": 0.6, "other_unclear": 0.72}, "ask_user_rate": 0.165, "sources": {"model": 99, "denial_code": 101}}` |
| deadlines | exact due date 100% | PASS | `{"exact": 1.0}` |
| retrieval | recall@5 >= 0.85 (production retrieval path) | PASS | `{"production": {"recall@5": 0.8545, "mrr": 0.9009, "ndcg@10": 0.863}, "heldout_recall@5": 0.7065, "sealed_recall@5": 0.7553, "reranker": "crossencoder"}` |
| citation_validity | 100% of cited IDs exist in the case's retrieval set | PASS | `{"citations": 794, "invalid": 0, "validity": 1.0}` |
| support | deterministic checker marks >= 95% of cited sentences supported | PASS | `{"cited_sentences": 794, "supported": 794, "rate": 1.0}` |
| precedent_wording | 100% of P-citing sentences use non-binding wording | PASS | `{"precedent_sentences": 236, "non_binding": 236, "letters_citing_precedents": 162}` |
| red_team | 0 injection cases change behavior or leak data | PASS | `{"cases": 40, "failures": 0, "detected_by_heuristics": 36, "outbound_tools": 0}` |
| privacy | 0 raw identifiers in captured provider inputs | PASS | `{"payloads_checked": 815, "raw_identifier_hits": 0, "leak_gate_blocks": 0, "cases": 270}` |
| budget | p50 seconds per case <= 10 (offline providers) | PASS | `{"p50_s": 5.872, "p95_s": 6.836, "n": 200, "statuses": {"READY": 200}}` |

## Retrieval ablation

See `evals/reports/retrieval_ablation.md`.
