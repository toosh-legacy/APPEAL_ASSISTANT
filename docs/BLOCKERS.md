# Blockers

Each entry: what blocked, what was tried, the fallback used, and what the developer should do.


## Retrieval recall@5 below the 0.85 gate (0.804)
- **What:** on the 66-question gold set, hybrid RRF + query rewriting reaches recall@5 0.804 (rules 0.764, precedents 0.875); MRR 0.819, nDCG@10 0.768. Full table and the per-question misses: `evals/reports/retrieval_ablation.md` (misses list) and `evals/reports/retrieval_per_question.json`.
- **Tried:** OR-keyword queries; weighted RRF; dictionary rewriting on both sides (hurt: 0.717), rewriting on the vector side only (best: 0.804); ts_rank_cd length normalizations 1/2/8/32 (no gain). Labels were also corrected to match section headings (a labeling bug, not tuning).
- **Why it misses:** most misses are near-misses: neighbouring paragraphs of the same section (e.g. 42 CFR 422.582(c)(1) instead of 422.582(b)) or the rights summary ranking just below 5. Labels are strict phrase matches, so a paraphrasing paragraph counts as a miss.
- **Fallback used:** none needed for the product — the Research agent always force-includes the cited deadline paragraphs (`required_ids`) and diversifies (procedural chunk + summary), so letters are unaffected. The eval gate is reported as FAIL.
- **Developer to do:** (1) add a cross-encoder or Azure AI Search semantic ranker (Phase C row); (2) review the strict labels and add graded relevance; (3) write held-out questions by hand (the dictionary was tuned on this set).
