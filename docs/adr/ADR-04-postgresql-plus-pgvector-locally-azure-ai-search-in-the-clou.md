# ADR-04: PostgreSQL + pgvector locally, Azure AI Search in the cloud

- **Status:** accepted (draft; rewrite in your own words in Phase B)
- **Date:** 2026-11-23

## Context
See SPEC.md section 23 and the sections referenced there.

## Decision
PostgreSQL + pgvector locally, Azure AI Search in the cloud.

## Alternatives considered
A vector-only database.

## Rationale
Legal text needs exact terms (regulation numbers) plus meaning; proven by the ablation.

## Where it lives in the code
`retrieval/retriever.py`, `evals/reports/retrieval_ablation.md`

## When to revisit
TODO (developer): write the trigger that would make you change this decision.
