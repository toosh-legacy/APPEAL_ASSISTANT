# ADR-01: Build locally behind interfaces, deploy to Azure by swapping adapters

- **Status:** accepted (draft; rewrite in your own words in Phase B)
- **Date:** 2026-11-23

## Context
See SPEC.md section 23 and the sections referenced there.

## Decision
Build locally behind interfaces, deploy to Azure by swapping adapters.

## Alternatives considered
Build directly on Azure.

## Rationale
Fast feedback, $0 development, tests without the cloud, portable design.

## Where it lives in the code
`appeal_core.interfaces`, `appeal_core.adapters.*`; `tests/test_azure_contracts.py`

## When to revisit
TODO (developer): write the trigger that would make you change this decision.
