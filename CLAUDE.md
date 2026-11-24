# CLAUDE.md

Source of truth: `SPEC.md`. If code and spec disagree, follow the spec. If the spec is ambiguous, choose the simplest option that meets the acceptance criteria and log it in `docs/DECISIONS.md`.

## Working rules (SPEC 0.2)
- Never stop to ask; log blockers in `docs/BLOCKERS.md`, use the documented fallback, continue.
- No `az`/`azd` and no cloud resources until Phase C. Model calls go to OpenAI only through the LiteLLM gateway (`packages/core/appeal_core/llm/gateway.py`); the key lives in git-ignored `.env`.
- Each phase ends with passing tests (`make test`), a local Conventional Commit, a `docs/CHANGELOG.md` entry and README updates. Never push.

## Layout (SPEC 19)
- `apps/web/` Next.js app · `services/api/` FastAPI · `services/worker/` orchestrator + agents
- `packages/core/` settings, interfaces, local + Azure adapters, privacy, retrieval, telemetry
- `packages/schemas/` JSON Schemas + `openapi.json` · `packages/prompts/` · `packages/kb/`
- `data/` pipeline, synth, processed, reports, manifest · `ml/` M1–M3 · `evals/` gold, runners, reports
- `infra/` Bicep stubs (Phase C) · `docs/` ADRs, reports

## Hard rules (SPEC 22, abridged)
1. No raw identifier reaches a model provider, log or trace; the leak gate fails closed.
2. No secrets in code; local keys are generated into git-ignored `.env`.
3. Never invent legal content; deadlines need a cited rule.
4. No agent tool sends data outside the case.
5. No cloud resources before Phase C. OpenAI is the model provider (developer decision), reached only through the LiteLLM gateway with a hard per-session budget; tests, CI and `make eval` use the LangChain fake chat model and never need a key; real calls run only in `make eval-live` and the app.
6. Every external dependency has a local adapter behind an interface; tests use it.
7. Behavior changes ship with tests; AI changes ship with eval results.
8. Synthetic data is unmistakably fake (Testperson names, ZZTEST IDs, 555-01xx, Example St).
9. Outcome stats are context, never advice against appealing.
10. Attribute datasets; show source disclaimers.
11. Never commit `data/raw/`; commit hashes in `data/manifest.json`.

## Commands
`make setup | up | data | train | eval | test | demo | lint` (each delegates to `uv run python tasks.py <name>`).
