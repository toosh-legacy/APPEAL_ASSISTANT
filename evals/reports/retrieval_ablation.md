# Retrieval ablation (SPEC 11.5)

Gold set: 66 questions (42 regulations/summaries, 24 precedents). Relevance labels come from text/metadata filters, not from the retriever (see `evals/appeal_evals/build_retrieval_gold.py`). recall@5 is normalized by min(|relevant|, 5).

| Configuration | recall@5 (all) | MRR (all) | nDCG@10 (all) | recall@5 rules | recall@5 precedents |
|---|---:|---:|---:|---:|---:|
| keyword only | 0.596 | 0.712 | 0.638 | 0.484 | 0.792 |
| vector only | 0.672 | 0.776 | 0.706 | 0.585 | 0.825 |
| hybrid RRF | 0.774 | 0.808 | 0.763 | 0.717 | 0.875 |
| hybrid RRF + query rewriting | 0.804 | 0.819 | 0.768 | 0.764 | 0.875 |
| hybrid RRF + rewriting + diversification (production) | 0.828 | 0.785 | 0.757 | 0.796 | 0.883 |

Notes:
- Query rewriting: the user's query feeds both keyword and vector search (weight 1.0); dictionary rewrites feed only the vector side (weight 0.25). Rewrites on the keyword side hurt (OR-queries with many legal terms match everything).
- Production adds SPEC 11.3 step 5 diversification (at least one procedural-rights chunk and one rights summary; both outcomes and same-subcategory/recent cases for precedents). It raises recall@5 but lowers MRR, because forced items can take the top slots.
- The rewrite dictionary and RRF weights were adjusted after inspecting misses on this gold set, so these numbers are optimistic; Phase B should add held-out questions written by a person.
- Precedent questions are answered without metadata filters here; in the product, Research also filters by the treatment category inferred from the service.

Phase C will add a fifth row: Azure AI Search hybrid + semantic ranker.

## Misses (production config, recall@5 < 1)

- `rq00` deadline to file internal appeal employer plan — recall@5 0.50, MRR 0.50
- `rq01` how many days do I have to appeal a denial from my job's health plan — recall@5 0.50, MRR 0.50
- `rq05` Medicare Advantage reconsideration filing deadline — recall@5 0.67, MRR 0.50
- `rq06` how long to appeal Medicare Advantage organization determination — recall@5 0.50, MRR 0.20
- `rq07` Medicaid managed care appeal deadline — recall@5 0.50, MRR 0.50
- `rq15` independent outside entity review when MA plan affirms denial — recall@5 0.67, MRR 0.50
- `rq16` continuation of benefits while medicaid appeal pending — recall@5 0.80, MRR 1.00
- `rq18` what must a denial notice say specific reason for adverse determination — recall@5 0.67, MRR 0.50
- `rq25` rescission of coverage counts as adverse benefit determination — recall@5 0.75, MRR 1.00
- `rq27` culturally and linguistically appropriate notices — recall@5 0.25, MRR 1.00
- `rq28` expedited external review urgent medical condition — recall@5 0.60, MRR 1.00
- `rq30` standard reconsideration Medicare Advantage decision 30 days — recall@5 0.40, MRR 1.00
- `rq31` who may request reconsideration Medicare Advantage — recall@5 0.00, MRR 0.00
- `rq33` good cause extension for filing reconsideration late — recall@5 0.40, MRR 1.00
- `rq35` medicaid plan must provide notice of adverse benefit determination in writing — recall@5 0.40, MRR 1.00
- `rq37` surprise billing out-of-network provider at in-network facility — recall@5 0.50, MRR 0.50
- `rq38` air ambulance out of network cost sharing — recall@5 0.75, MRR 1.00
- `rq39` notice and consent to waive balance billing protections — recall@5 0.60, MRR 1.00
- `pq00` MRI lumbar spine medical necessity — recall@5 0.80, MRR 1.00
- `pq02` residential treatment center eating disorder — recall@5 0.20, MRR 0.25
- `pq03` residential treatment substance use disorder — recall@5 0.80, MRR 1.00
- `pq07` gastric bypass bariatric surgery obesity — recall@5 0.00, MRR 0.11
- `pq08` IVIG immune globulin infusion — recall@5 0.80, MRR 0.50
- `pq09` genetic testing hereditary cancer BRCA — recall@5 0.60, MRR 1.00
