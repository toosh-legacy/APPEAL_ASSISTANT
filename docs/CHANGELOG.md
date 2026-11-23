# Changelog

## Phase 0 · Scaffold
- Monorepo layout (SPEC 19), uv project (Python 3.12), root package.json, docker-compose (pgvector, Redis, Azurite + profiles), Makefile → tasks.py, .env.example, CLAUDE.md, pre-commit, CI workflow.
- SQLAlchemy models for all section-12 tables and Alembic migration 0001 (pgvector, GIN + HNSW indexes).
- Environment detection → full mode (docs/ENVIRONMENT.md).

## Phase 1 · Data pipeline
- D1 IMR: download → validate (exact-duplicate drop, unique IDs) → clean → regex PII scan/mask → profile (`data/reports/imr_profile.md`, PNG charts) → load `imr_case`, `imr_stats`, `precedent_chunk`. 42,710 real decisions.
- D1 data dictionary summary (`data/reports/imr_dictionary.md`), including dictionary-vs-file discrepancies.
- D2 eCFR: 9 sources fetched for their `up_to_date_as_of` date, parsed into a paragraph hierarchy with citation paths, chunked, topic-tagged, loaded into `kb_chunk` (406 chunks).
- D4 synthetic letters: 3,000 train / 500 validation / 120 gold (gold committed in `evals/gold/letters.jsonl`).
- D5: rights summaries, 8 playbooks, denial-code map, cited deadline rules with phrase-based citation resolution.
- `data/manifest.json` with hashes; data tests.

## Phase 2 · Backend vertical slice
- Agent contracts (Pydantic → `packages/schemas/*.schema.json`), state machine domain service with optimistic concurrency, audit events.
- Postgres job queue + outbox (SKIP LOCKED, leases, retries with backoff + jitter, dead-lettering); Azurite blob store with write-only SAS; Redis progress bus → SSE with `Last-Event-ID` resume.
- Privacy: regex + Presidio PII detection, tokenization vault with envelope encryption, fail-closed leak gate on every provider call, scrubbing JSON logger, OTel spans.
- Offline provider (extraction rules, playbook writer, query rewriting) and the five agents; checkpointed, idempotent orchestrator with a ≤2-revision Writer⇄Reviewer loop, NEEDS_CATEGORY / NEEDS_HUMAN states, degraded mode.
- FastAPI `/v1` endpoints (uploads, cases, events, extraction, category, letter get/put/regenerate, precedents, exports PDF/DOCX/ICS, delete, kb chunks, insights flag), admin endpoints, health probes, Problem Details, correlation IDs, token-bucket rate limits.
- Tests: every state edge, privacy round trips (Hypothesis), leak gate, log scrubbing, queue semantics, API flow RECEIVED→READY, crash-resume without re-running steps.

## Phase 3 · Retrieval
- MiniLM (all-MiniLM-L6-v2) embedder with TF-IDF+SVD (LSA) fallback; all `kb_chunk` and `precedent_chunk` rows embedded (`make data` step `embed`, idempotent).
- Hybrid retriever: Postgres full-text (`ts_rank_cd`, GIN) + pgvector cosine (HNSW) → RRF (k=60) → diversification (procedural-rights chunk, rights summary, both outcomes for precedents, same-subcategory/recency preference); required deadline-basis chunks always included.
- `imr_stats` cards with Wilson 95% intervals and by-year trend; `/v1/cases/{id}/precedents`, `/v1/kb/chunks/{id}`.
- Retrieval gold set (66 questions: 42 regulations/summaries, 24 precedents) with filter-defined relevance; metrics runner and ablation report.

## Phase 4 · Machine learning
- M1 denial-category classifier (TF-IDF word+char + code indicators; LR vs calibrated linear SVM), temperature scaling and ask-user threshold from grouped out-of-fold predictions, code-map override, no-codes ablation.
- M2 IMR-type classifier on real Findings text with time-based split, TF-IDF vs MiniLM-embedding variants and a shortcut-phrase ablation.
- M3 overturn-rate model (LR one-hot vs HistGradientBoosting) against overall and empirical-Bayes baselines, calibration, by-year drift, age/gender fairness slices (not features).
- Local ModelRegistry with pinned versions, promotion check (≤ 1 point regression), `ml/reports/latest.md`; M1 wired into the Classifier, M2/M3 into Research.

## Phase 5 · Frontend
- Next.js 15 (App Router, TypeScript strict, Tailwind, TanStack Query, React Hook Form + Zod, Radix Dialog) with `/`, `/start`, `/cases/[id]/confirm`, `/cases/[id]` (SSE progress, explanation / category picker, deadline + .ics, similar cases with stats and explainer, letter editor with footnote dialogs, regenerate, placeholders blocking export, evidence kit, delete), `/sources/[chunkId]`, `/about/data`, `/insights/insurers` (flagged).
- Types generated from `packages/schemas/openapi.json`; Playwright happy path + axe on desktop and mobile using the installed Chrome.
