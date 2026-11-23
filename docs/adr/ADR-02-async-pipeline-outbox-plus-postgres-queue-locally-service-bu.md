# ADR-02: Async pipeline (outbox + Postgres queue locally, Service Bus in the cloud)

- **Status:** accepted (draft; rewrite in your own words in Phase B)
- **Date:** 2026-11-23

## Context
See SPEC.md section 23 and the sections referenced there.

## Decision
Async pipeline (outbox + Postgres queue locally, Service Bus in the cloud).

## Alternatives considered
Synchronous HTTP.

## Rationale
Multi-step, slow AI chains; retries; crash recovery; per-case ordering.

## Where it lives in the code
`adapters/queue_postgres.py` (job row inserted in the same transaction as the state change)

## When to revisit
TODO (developer): write the trigger that would make you change this decision.
