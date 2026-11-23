# Appeal Assistant

A multi-agent assistant that helps patients appeal denied health insurance claims, grounded in real California DMHC Independent Medical Review decisions and federal regulations (eCFR). Built locally first (no cloud, no API keys); Azure deployment comes later (see `SPEC.md`).

> Not legal or medical advice. The user is always the author of their appeal.

## Quick start (local, full mode with Docker)
```bash
make setup     # uv sync + generate .env with local keys
make up        # Postgres+pgvector, Redis, Azurite; run migrations
make data      # download + validate + load datasets, generate synthetic letters
make train     # train M1-M3
make eval      # run every eval suite -> evals/reports/latest.md
make test      # pytest
make demo      # API + in-process worker + web
```
Without `make`, use `uv run python tasks.py <target>`.

Host ports: Postgres 55432, Redis 56379, Azurite 10000, API 8000, web 3100.

## Status
See `docs/MORNING_REPORT.md`, `docs/CHANGELOG.md`, `docs/DECISIONS.md` and `docs/BLOCKERS.md`.

## Data attribution
- Independent Medical Review data: **California Department of Managed Health Care** (CC BY), via the California Health and Human Services Open Data Portal.
- Federal regulations: eCFR (public domain).
