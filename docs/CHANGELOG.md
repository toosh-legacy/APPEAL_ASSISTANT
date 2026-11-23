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
