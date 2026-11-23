"""Writes the ADR skeletons from SPEC section 23. The developer rewrites them in their own words in Phase B."""

from pathlib import Path

ADRS = [
    ("01", "Build locally behind interfaces, deploy to Azure by swapping adapters", "Build directly on Azure", "Fast feedback, $0 development, tests without the cloud, portable design", "`appeal_core.interfaces`, `appeal_core.adapters.*`; `tests/test_azure_contracts.py`"),
    ("02", "Async pipeline (outbox + Postgres queue locally, Service Bus in the cloud)", "Synchronous HTTP", "Multi-step, slow AI chains; retries; crash recovery; per-case ordering", "`adapters/queue_postgres.py` (job row inserted in the same transaction as the state change)"),
    ("03", "A hand-built persisted state machine", "Microsoft Agent Framework, LangGraph, Durable Functions", "Explainable checkpoints, idempotency and human-in-the-loop states; revisit when contracts stabilize", "`state_machine.py`, `appeal_worker/orchestrator.py` (step output + transition in one transaction)"),
    ("04", "PostgreSQL + pgvector locally, Azure AI Search in the cloud", "A vector-only database", "Legal text needs exact terms (regulation numbers) plus meaning; proven by the ablation", "`retrieval/retriever.py`, `evals/reports/retrieval_ablation.md`"),
    ("05", "Tokenize identifiers before any model call", "Trust vendor terms", "Data minimization; testable; smaller blast radius", "`privacy/vault.py`, `privacy/leak_gate.py`, privacy eval suite"),
    ("06", "Sentence-level structured citations", "Free-text letters", "Mechanical verification", "`schemas.LetterDraft`, `agents.review`"),
    ("07", "ML classifier first, LLM fallback", "LLM only", "Cheaper, calibrated, measurable", "`ml/appeal_ml/m1.py`, `agents.classify`"),
    ("08", "Real IMR outcomes as precedents and statistics", "Generic advice only", "Grounds arguments in real independent-review reasoning; a strong differentiator", "`data/pipeline/appeal_data/imr.py`, `retrieval/imr_stats.py`"),
    ("09", "Time-based splits for M2/M3", "Random splits", "Avoids leaking the future into the past; mirrors deployment", "`ml/appeal_ml/m2.py::time_split`"),
    ("10", "Exclude age and gender as M3 features but report fairness slices", "Use all fields", "Avoids encoding demographic effects into advice-like output while still measuring disparities", "`ml/appeal_ml/m3.py`, M3 model card"),
]

if __name__ == "__main__":
    here = Path(__file__).parent
    for n, decision, alt, why, where in ADRS:
        slug = decision.lower().replace(" ", "-").replace(",", "").replace("(", "").replace(")", "").replace("/", "-").replace("+", "plus")[:60]
        (here / f"ADR-{n}-{slug}.md").write_text(
            f"# ADR-{n}: {decision}\n\n- **Status:** accepted (draft; rewrite in your own words in Phase B)\n- **Date:** 2026-11-23\n\n"
            f"## Context\nSee SPEC.md section 23 and the sections referenced there.\n\n## Decision\n{decision}.\n\n"
            f"## Alternatives considered\n{alt}.\n\n## Rationale\n{why}.\n\n## Where it lives in the code\n{where}\n\n"
            "## When to revisit\nTODO (developer): write the trigger that would make you change this decision.\n",
            encoding="utf-8",
        )
    print("wrote", len(ADRS), "ADRs")
