# Retrieval ablation (SPEC 11.5)

- **Dev set** `evals/gold/retrieval.jsonl`: 66 questions (42 regulations/summaries, 24 precedents). The rewrite dictionary and RRF weights were tuned on it, so its numbers are optimistic. The SPEC gate is measured here.
- **Held-out #1** `retrieval_heldout.jsonl`: 28 questions written after the dev work, labels fixed before any run. Its failure *types* were then inspected to design the diversification fixes, so it is no longer fully unseen.
- **Sealed** `retrieval_sealed.jsonl`: 19 questions written before those fixes and run once after the configuration was frozen. The most honest number here.
- Labels come from text/metadata rules, never from the retriever (`evals/appeal_evals/build_retrieval_gold.py`). recall@5 is normalized by min(|relevant|, 5).

| Configuration | dev recall@5 | dev MRR | dev nDCG@10 | dev rules | dev precedents | held-out #1 recall@5 | sealed recall@5 |
|---|---:|---:|---:|---:|---:|---:|---:|
| keyword only | 0.611 | 0.718 | 0.652 | 0.488 | 0.825 | — | — |
| vector only | 0.706 | 0.814 | 0.738 | 0.590 | 0.908 | — | — |
| hybrid RRF | 0.804 | 0.850 | 0.794 | 0.721 | 0.950 | — | — |
| hybrid RRF + query rewriting | 0.838 | 0.861 | 0.800 | 0.773 | 0.950 | — | — |
| hybrid RRF + rewriting + diversification | 0.835 | 0.861 | 0.809 | 0.773 | 0.942 | 0.653 | 0.676 |
| hybrid RRF + rewriting + diversification + cross-encoder rerank (production) | 0.855 | 0.901 | 0.863 | 0.824 | 0.908 | 0.707 | 0.755 |

Notes:
- Query rewriting: the user's query feeds both keyword and vector search (weight 1.0); dictionary rewrites feed only the vector side (weight 0.25). Rewrites on the keyword side hurt (OR-queries with many legal terms match everything).
- Diversification (SPEC 11.3 step 5): required deadline chunks first; at least one procedural-rights chunk and exactly one rights summary, kept at their natural rank; 'Definitions' sections moved back unless the question asks what something means; both outcomes and same-subcategory/recent cases for precedents.
- Reranker: cross-encoder/ms-marco-MiniLM-L-6-v2 (local, CPU) reorders the top 30 fused candidates by the user's query. Top-30 was fixed before measuring, not tuned. Costs about 1 s per search on a laptop CPU.
- Precedent questions are answered without metadata filters here; in the product, Research also filters by the treatment category inferred from the service.

Phase C will add a row: Azure AI Search hybrid + semantic ranker.

## Misses (production config, dev set, recall@5 < 1)

- `rq00` deadline to file internal appeal employer plan — recall@5 0.50, MRR 1.00
- `rq06` how long to appeal Medicare Advantage organization determination — recall@5 0.00, MRR 0.12
- `rq10` copies of documents relevant to my claim free of charge — recall@5 0.75, MRR 1.00
- `rq15` independent outside entity review when MA plan affirms denial — recall@5 0.67, MRR 1.00
- `rq16` continuation of benefits while medicaid appeal pending — recall@5 0.80, MRR 1.00
- `rq18` what must a denial notice say specific reason for adverse determination — recall@5 0.33, MRR 0.50
- `rq27` culturally and linguistically appropriate notices — recall@5 0.75, MRR 1.00
- `rq28` expedited external review urgent medical condition — recall@5 0.80, MRR 1.00
- `rq30` standard reconsideration Medicare Advantage decision 30 days — recall@5 0.40, MRR 0.50
- `rq31` who may request reconsideration Medicare Advantage — recall@5 0.40, MRR 0.33
- `rq33` good cause extension for filing reconsideration late — recall@5 0.80, MRR 1.00
- `rq34` medicaid grievance filed at any time — recall@5 0.00, MRR 0.17
- `rq35` medicaid plan must provide notice of adverse benefit determination in writing — recall@5 0.60, MRR 1.00
- `rq37` surprise billing out-of-network provider at in-network facility — recall@5 0.50, MRR 1.00
- `rq38` air ambulance out of network cost sharing — recall@5 0.50, MRR 1.00
- `rq39` notice and consent to waive balance billing protections — recall@5 0.80, MRR 0.50
- `pq00` MRI lumbar spine medical necessity — recall@5 0.80, MRR 0.50
- `pq06` transcranial magnetic stimulation depression — recall@5 0.80, MRR 1.00
- `pq08` IVIG immune globulin infusion — recall@5 0.80, MRR 1.00
- `pq09` genetic testing hereditary cancer BRCA — recall@5 0.20, MRR 0.33
- `pq10` viscosupplementation knee injection osteoarthritis — recall@5 0.80, MRR 1.00
- `pq12` artificial disc replacement cervical — recall@5 0.80, MRR 1.00
- `pq23` experimental treatment clinical trial cancer drug — recall@5 0.60, MRR 1.00
