# Appeal Assistant

A multi-agent assistant that helps patients appeal denied health insurance claims, grounded in **real California DMHC Independent Medical Review decisions** and **federal regulations (eCFR)**. Built local-first: no cloud resources, no paid APIs, no API keys. Azure deployment is Phase C (see `SPEC.md`, `infra/README.md`).

> Not legal or medical advice. The user is always the author of their appeal and sends it themselves.

## Quick start (full mode: Docker Desktop)
```bash
make setup     # uv sync (Python 3.12) + generate .env with local keys
make up        # Postgres 16 + pgvector, Redis, Azurite; run migrations
make data      # download/validate/profile/load IMR + eCFR, synthetic letters, KB, embeddings
make train     # train M1-M3, write model cards and ml/reports/latest.md
make eval      # every eval suite -> evals/reports/latest.md
make test      # pytest
make demo      # API on :8000 (in-process worker) + web app on :3100
```
Without `make`: `uv run python tasks.py <target>`. Web e2e: `cd apps/web && npx playwright test` (uses your installed Chrome) while `make demo` runs.

Host ports: Postgres 55432, Redis 56379, Azurite 10000, API 8000, web 3100.

## How it works
1. **Upload or paste** a denial letter (`/start`). Files go to blob storage through a 10-minute write-only SAS URL.
2. **Intake** detects identifiers (regex + Presidio), replaces them with vault tokens (envelope-encrypted per case), checks for prompt injection, and extracts fields — the model only ever sees tokenized text, and a **fail-closed leak gate** guards every provider call.
3. You **confirm the facts** (`/cases/<id>/confirm`).
4. **Classifier** (M1 + denial-code map; asks you when unsure) → **Research** (hybrid retrieval over regulations, rights summaries and 52k IMR precedent chunks; cited deadline rules; Wilson-interval stats; M2/M3) → **Writer** (sentences with citation IDs) ⇄ **Reviewer** (citation validity, support checker, banned wording, ≤ 2 revisions).
5. The **workspace** (`/cases/<id>`) streams progress over SSE and shows the explanation, your cited deadline (+ .ics), similar California reviews, the letter editor with footnotes, and the evidence kit. Placeholders block PDF/DOCX export until filled.

## Repository layout
`apps/web` Next.js · `services/api` FastAPI · `services/worker` orchestrator + agents · `packages/core` settings, interfaces, adapters, privacy, retrieval · `packages/kb` summaries, playbooks, denial codes, deadline rules · `data/` pipeline, synthetic generator, reports, manifest · `ml/` M1–M3 · `evals/` gold sets, runners, reports · `infra/` Bicep stubs · `docs/` ADRs, decisions, blockers, morning report.

## Data pipeline
`make data` downloads the DMHC IMR file and the eCFR sections, validates, profiles (`data/reports/imr_profile.md`) and loads them, generates the synthetic letters and embeds all chunks. A second run skips unchanged files. Raw files are never committed; their hashes are in `data/manifest.json`.

## Backend
`make up`, then `make api` and `make worker` (or `make demo`). OpenAPI docs at http://127.0.0.1:8000/docs; the spec is exported to `packages/schemas/openapi.json` and the TypeScript types are generated from it (`npm run gen:api`).

## Models and evaluation
- Model cards: `ml/artifacts/m1|m2|m3/v1/model_card.md`; summary: `ml/reports/latest.md`.
- **M1 is trained and evaluated on synthetic letters only**; expect lower accuracy on real letters (see its model card).
- Evaluation report with every gate: `evals/reports/latest.md`; retrieval ablation: `evals/reports/retrieval_ablation.md`.

## Status
See `docs/MORNING_REPORT.md`, `docs/CHANGELOG.md`, `docs/DECISIONS.md` and `docs/BLOCKERS.md`.
**All rights summaries and deadline rules are marked `needs_human_review` and must be checked by a person before anything is public.**

## Data attribution
- Independent Medical Review data: **California Department of Managed Health Care** (CC BY), via the California Health and Human Services Open Data Portal.
- Federal regulations: eCFR (public domain).
