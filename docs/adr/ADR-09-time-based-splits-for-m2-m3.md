# ADR-09: Time-based splits for M2/M3

- **Status:** accepted (draft; rewrite in your own words in Phase B)
- **Date:** 2026-11-23

## Context
See SPEC.md section 23 and the sections referenced there.

## Decision
Time-based splits for M2/M3.

## Alternatives considered
Random splits.

## Rationale
Avoids leaking the future into the past; mirrors deployment.

## Where it lives in the code
`ml/appeal_ml/m2.py::time_split`

## When to revisit
TODO (developer): write the trigger that would make you change this decision.
