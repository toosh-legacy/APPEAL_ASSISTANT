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

## Phase 6 · Evaluation, red team, privacy gate
- `make eval` runs every SPEC 17.2 suite through the real orchestrator + DB and writes `evals/reports/latest.md|json` plus `eval_run` rows; exit code 1 on a failing blocking gate. `--fast` subset for CI.
- 40 red-team letters (ignore-previous, fake system tags, hidden footer comments, other users' data, threats/false claims, base64, claims-processor notes, zero-width characters, ...) and 30 privacy probes (split IDs, initials, middle initials, phone formats, emails, DOB, MRN, SSN) in `evals/gold/`.
- Results: all gates pass except retrieval recall@5 (0.804 vs 0.85; logged in BLOCKERS). Red team 0/40 failures; privacy 0 raw identifiers in 621 captured provider inputs.
- CI: `--ci` data mode (synthetic IMR sample + LSA embeddings) so the fast evals run without the 85 MB download.

## Phase 7 · Phase C preparation (no cloud calls)
- `infra/README.md` mapping every SPEC 7.2 resource to its Bicep module, the local adapter it replaces, the switch and the env vars; 19 stub modules + `main.bicep`, parameters per environment, `azure.yaml` (nothing deployed).
- Azure adapter classes raise `NotConfigured` naming the missing variables; `tests/test_azure_contracts.py` checks every switch fails clearly without credentials and skips live contract tests.
- ADR skeletons (`docs/adr/`) and the STRIDE threat model (`docs/threat-model.md`).

## P1 tasks
- D3: CMS Transparency in Coverage PUF (2027 release, plan-year 2025 data) → `insurer_stats` (136 individual-Marketplace issuers); F9 `/insights/insurers` enabled with CMS's own disclaimer; exact-name insurer line on the explanation card.
- Admin page (`/admin`): eval runs, data-refresh status, redacted case traces with per-agent latency, prompt versions and tokens.
- Playwright: 8 tests (desktop + mobile) incl. axe on insights and admin pages.

## Hardening (after the first morning report)
- Retention purge (`make retention`): expired uploads lose blob + stored text; expired cases are deleted (vault key destroyed). Tested.
- One trace per case: W3C trace context is stored in the job payload by the API and continued by the worker (`job.*` → `agent.*` spans). Tested.
- `/admin/v1/metrics`: p50 latency per agent, revisions per case, NEEDS_HUMAN rate, ask-user rate, leak-gate blocks, injection detections, cost per case.
- Hypothesis property tests for deadline math and .ics; text-PDF upload path test (SAS PUT → Azurite → pypdf → intake).
