# Blockers

Each entry: what blocked, what was tried, the fallback used, and what the developer should do.


## Retrieval: dev gate now passes (0.855), but unseen questions score 0.71–0.76
- **Status (2026-11-23, Phase B):** the SPEC gate (dev set) passes at recall@5 0.855 after label fixes (v2), diversification fixes and a local cross-encoder reranker. On questions written after the tuning it is lower: held-out #1 0.707, sealed 0.755. Rules questions remain the weak spot on held-out (≈0.60). Details: `evals/reports/retrieval_ablation.md`, `docs/DECISIONS.md` (Phase B).
- **Tried:** OR-keyword queries; weighted RRF; dictionary rewriting (vector side only); ts_rank_cd normalizations; label v2; summary cap + definitions demotion; cross-encoder top-30 rerank (helps unseen questions, slightly hurts dev precedents).
- **Remaining misses:** neighbouring paragraphs of the right section (e.g. 42 CFR 438.408(b)(1) instead of (c)(1)) and fast-track 422.626 beating 422.590(e) for "fast appeal" questions.
- **Fallback used:** none needed by the product — Research force-includes the cited deadline paragraphs, so letters are unaffected.
- **Developer to do:** (1) write 30+ held-out questions yourself (not by the author of the retriever) and make that the gate; (2) graded relevance (neighbouring paragraphs = partial credit); (3) Phase C: Azure AI Search semantic ranker row; (4) consider a legal-domain reranker.
