# ADR-07: ML classifier first, LLM fallback

- **Status:** accepted (draft; rewrite in your own words in Phase B)
- **Date:** 2026-11-23

## Context
See SPEC.md section 23 and the sections referenced there.

## Decision
ML classifier first, LLM fallback.

## Alternatives considered
LLM only.

## Rationale
Cheaper, calibrated, measurable.

## Where it lives in the code
`ml/appeal_ml/m1.py`, `agents.classify`

## When to revisit
TODO (developer): write the trigger that would make you change this decision.
