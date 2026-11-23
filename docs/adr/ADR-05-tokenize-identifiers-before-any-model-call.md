# ADR-05: Tokenize identifiers before any model call

- **Status:** accepted (draft; rewrite in your own words in Phase B)
- **Date:** 2026-11-23

## Context
See SPEC.md section 23 and the sections referenced there.

## Decision
Tokenize identifiers before any model call.

## Alternatives considered
Trust vendor terms.

## Rationale
Data minimization; testable; smaller blast radius.

## Where it lives in the code
`privacy/vault.py`, `privacy/leak_gate.py`, privacy eval suite

## When to revisit
TODO (developer): write the trigger that would make you change this decision.
