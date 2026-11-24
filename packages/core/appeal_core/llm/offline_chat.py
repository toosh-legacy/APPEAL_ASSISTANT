"""A LangChain fake chat model that answers every structured-output request with the deterministic offline
rules (extraction regexes, playbook writer, dictionary query rewriting).

It is a real `BaseChatModel`, so tests and CI run the exact same LangChain chains (prompt template ->
`.with_structured_output(...)`) as production, with no network, no key and no cost. Set LLM_PROVIDER=openai
to swap in `ChatOpenAI`; nothing else changes.
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.prompt_values import PromptValue
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel

from appeal_core.llm.contracts import CategoryOut, DraftOut, ExtractionOut, QueryRewrites, ReviewOut

_DOC = re.compile(r"<document>\n?(.*?)\n?</document>", re.S)
_REQ = re.compile(r"<request>\n?(.*?)\n?</request>", re.S)


def _human_text(inp: Any) -> str:
    msgs: list[BaseMessage] = inp.to_messages() if isinstance(inp, PromptValue) else list(inp)
    return str(msgs[-1].content)


def _request(text: str) -> dict[str, Any]:
    m = _REQ.search(text)
    return json.loads(m.group(1)) if m else {}


def _answer(schema: type[BaseModel], text: str) -> BaseModel:
    from appeal_core.llm.offline import offline_extract, offline_rewrite, offline_write

    if schema is ExtractionOut:
        m = _DOC.search(text)
        fields = offline_extract(m.group(1) if m else text)["fields"]
        vals = {k: fv["value"] for k, fv in fields.items()}
        vals["denial_codes"] = vals.get("denial_codes") or []
        return ExtractionOut.model_validate(vals)
    if schema is CategoryOut:  # the rules have no opinion beyond M1: zero confidence, so M1/user decide
        return CategoryOut(
            category="other_unclear", confidence=0.0, rationale="offline rules do not classify"
        )
    if schema is QueryRewrites:
        return QueryRewrites(queries=offline_rewrite(_request(text)["query"]))
    if schema is DraftOut:
        sections = offline_write(_request(text))["sections"]
        for sec in sections:
            for s in sec["sentences"]:
                s.setdefault("argument_id", None)
        return DraftOut.model_validate({"sections": sections})
    if schema is ReviewOut:
        return ReviewOut(issues=[])
    raise NotImplementedError(f"offline chat model has no rule for {schema.__name__}")


class OfflineChatModel(BaseChatModel):
    model_name: str = "offline-rules-v1"

    @property
    def _llm_type(self) -> str:
        return "offline-rules"

    def _generate(
        self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: Any = None, **kw: Any
    ) -> ChatResult:
        msg = AIMessage(
            content="{}", usage_metadata={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        )
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def with_structured_output(self, schema: Any, **kw: Any) -> Runnable:  # type: ignore[override]
        return RunnableLambda(
            lambda inp: _answer(schema, _human_text(inp)), name=f"offline:{schema.__name__}"
        )
