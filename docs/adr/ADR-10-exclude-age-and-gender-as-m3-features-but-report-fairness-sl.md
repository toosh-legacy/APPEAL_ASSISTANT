# ADR-10: Exclude age and gender as M3 features but report fairness slices

- **Status:** accepted (draft; rewrite in your own words in Phase B)
- **Date:** 2026-11-23

## Context
See SPEC.md section 23 and the sections referenced there.

## Decision
Exclude age and gender as M3 features but report fairness slices.

## Alternatives considered
Use all fields.

## Rationale
Avoids encoding demographic effects into advice-like output while still measuring disparities.

## Where it lives in the code
`ml/appeal_ml/m3.py`, M3 model card

## When to revisit
TODO (developer): write the trigger that would make you change this decision.
