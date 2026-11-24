"""promptfoo Python provider: runs one uploaded letter through the real intake (PII tokenization, injection
detection, structured extraction) and writer chains, and returns what an attacker could influence.

LLM_PROVIDER=offline (CI): the LangChain fake chat model. LLM_PROVIDER=openai: the same chains on OpenAI via
the LiteLLM gateway (budget-capped). Retrieval is not needed: the writer gets no sources, so any legal claim
it makes would be invented and is caught by the assertions.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in ("packages/core", "services/worker", "services/api"):
    sys.path.insert(0, str(ROOT / p))


def call_api(prompt: str, options: dict, context: dict) -> dict:
    from appeal_core.schemas import Research
    from appeal_worker import agents

    letter = context["vars"]["letter"]
    raw_ids = context["vars"].get("identifiers") or []
    ext, tokenized, tmap = agents.intake(letter)
    facts = {k: v.value for k, v in ext.fields.items()}
    facts["member_name"] = next((t for t in tmap.tokens if t.startswith("[PERSON_")), None)
    draft = agents.write(facts, "other_unclear", Research(rules=[], precedents=[]), tmap.raw_values())
    body = " ".join(s.text for sec in draft.sections for s in sec.sentences)
    out = {
        "injection_flags": ext.injection_flags,
        "denial_reason": facts.get("denial_reason"),
        "letter": body,
        "legal_sentences_without_sources": sum(1 for sec in draft.sections for s in sec.sentences if s.kind == "legal"),
        "raw_identifier_reached_model": any(r and r in tokenized for r in raw_ids if len(r) >= 6),
    }
    return {"output": json.dumps(out)}
