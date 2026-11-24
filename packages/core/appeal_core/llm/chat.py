"""The LLM provider every agent uses: one LangChain chain per step,

    ChatPromptTemplate (from packages/prompts/*.yaml) | chat_model.with_structured_output(<Pydantic contract>)

run inside `guarded_call`, so the leak gate checks the exact variables before anything leaves the process.
Cheap tier: extraction, classification, query rewriting. Strong tier: writer and reviewer.
The chat model comes from the LiteLLM gateway (`gateway.get_chat`); offline it is `OfflineChatModel`.
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from appeal_core.llm.base import guarded_call, prompt
from appeal_core.llm.contracts import CategoryOut, DraftOut, ExtractionOut, QueryRewrites, ReviewOut
from appeal_core.llm.cost import get_ledger
from appeal_core.llm.gateway import get_chat, model_id, moderate
from appeal_core.llm.merge import merge_fields
from appeal_core.llm.offline import offline_extract
from appeal_core.settings import get_settings

_PH = re.compile(r"\[ADD: [^\]]+\]")


def template(prompt_id: str) -> ChatPromptTemplate:
    p = prompt(prompt_id)
    return ChatPromptTemplate.from_messages([("system", p["system"]), ("human", p["user"])])


class LLMProvider:
    """Same interface for offline and hosted models; only the chat model behind the chain changes."""

    def __init__(self) -> None:
        self.name = get_settings().llm_provider

    def _run(
        self,
        tier: str,
        prompt_id: str,
        out: type[BaseModel],
        variables: dict[str, str],
        raw_values: list[str],
    ) -> Any:
        chain = template(prompt_id) | get_chat(tier).with_structured_output(out)
        before = get_ledger().spent
        result, rec = guarded_call(
            self.name, model_id(tier), prompt_id, variables, raw_values, lambda v: chain.invoke(v)
        )
        rec.cost_usd = round(max(0.0, get_ledger().spent - before), 6)  # priced by LiteLLM, not estimated
        return result

    # ------------------------------------------------------------------ intake (cheap tier)
    def extract(self, tokenized_text: str, case_raw_values: list[str]) -> dict[str, Any]:
        base = offline_extract(tokenized_text)
        tier = "fast-ft" if get_settings().openai_fine_tuned_model else "fast"
        got: ExtractionOut = self._run(
            tier, "intake_extract", ExtractionOut, {"document": tokenized_text}, case_raw_values
        )
        return merge_fields(base, got.model_dump(), tokenized_text)

    # ------------------------------------------------------------------ classifier fallback (cheap tier)
    def classify(
        self, reason: str | None, codes: list[str], service: str | None, case_raw_values: list[str], letter: str | None = None
    ) -> CategoryOut:
        # the whole (tokenized) letter: given only the reason line, the model misread prior-authorization denials
        req = json.dumps({"reason": reason, "codes": codes, "service": service, "letter": (letter or "")[:6000]}, ensure_ascii=False)
        tier = "fast-ft" if get_settings().openai_fine_tuned_model else "fast"
        return self._run(tier, "classifier_category", CategoryOut, {"request": req}, case_raw_values)

    # ------------------------------------------------------------------ research (cheap tier, semantic cache)
    def rewrite_query(self, query: str, case_raw_values: list[str]) -> list[str]:
        if self.name == "openai":
            get_ledger().lookup()  # one semantic-cache lookup per rewrite call
        got: QueryRewrites = self._run(
            "rewrite",
            "query_rewrite",
            QueryRewrites,
            {"request": json.dumps({"query": query})},
            case_raw_values,
        )
        return [q for q in got.queries if q.strip()][:3]

    # ------------------------------------------------------------------ writer (strong tier)
    def write(self, request: dict[str, Any], case_raw_values: list[str]) -> dict[str, Any]:
        got: DraftOut = self._run(
            "strong",
            "writer_letter",
            DraftOut,
            {"request": json.dumps(request, ensure_ascii=False, default=str)},
            case_raw_values,
        )
        sections = got.model_dump()["sections"]
        placeholders: list[str] = []
        for sec in sections:
            for s in sec["sentences"]:
                for m in _PH.findall(s["text"]):
                    if m not in placeholders:
                        placeholders.append(m)
        return {
            "sections": sections,
            "placeholders": placeholders,
            "revision": request.get("revision", 0),
            "degraded": False,
        }

    # ------------------------------------------------------------------ reviewer (strong tier)
    def review(
        self,
        draft: dict[str, Any],
        sources: dict[str, Any],
        facts: dict[str, Any],
        case_raw_values: list[str],
    ) -> ReviewOut:
        req = json.dumps(
            {"draft": draft, "sources": sources, "facts": facts}, ensure_ascii=False, default=str
        )
        return self._run("strong", "reviewer_letter", ReviewOut, {"request": req}, case_raw_values)

    # ------------------------------------------------------------------ output safety
    def moderate(self, text: str, case_raw_values: list[str]) -> list[str]:
        from appeal_core.privacy.leak_gate import check_payload

        check_payload({"text": text}, case_raw_values)
        return moderate(text)
