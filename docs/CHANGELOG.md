# Changelog

## Phase 0 · Scaffold
- Monorepo layout (SPEC 19), uv project (Python 3.12), root package.json, docker-compose (pgvector, Redis, Azurite + profiles), Makefile → tasks.py, .env.example, CLAUDE.md, pre-commit, CI workflow.
- SQLAlchemy models for all section-12 tables and Alembic migration 0001 (pgvector, GIN + HNSW indexes).
- Environment detection → full mode (docs/ENVIRONMENT.md).
