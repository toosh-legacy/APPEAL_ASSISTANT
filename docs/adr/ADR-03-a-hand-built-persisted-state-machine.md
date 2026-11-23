# ADR-03: A hand-built persisted state machine

- **Status:** accepted (draft; rewrite in your own words in Phase B)
- **Date:** 2026-11-23

## Context
See SPEC.md section 23 and the sections referenced there.

## Decision
A hand-built persisted state machine.

## Alternatives considered
Microsoft Agent Framework, LangGraph, Durable Functions.

## Rationale
Explainable checkpoints, idempotency and human-in-the-loop states; revisit when contracts stabilize.

## Where it lives in the code
`state_machine.py`, `appeal_worker/orchestrator.py` (step output + transition in one transaction)

## When to revisit
TODO (developer): write the trigger that would make you change this decision.
