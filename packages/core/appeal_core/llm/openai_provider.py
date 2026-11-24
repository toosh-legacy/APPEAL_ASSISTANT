"""Hosted OpenAI provider (Phase B, developer-approved): LLM_PROVIDER=openai.

Same contracts as the offline provider, and every call still goes through `guarded_call`, so the leak gate
runs before any text leaves the machine. Only TOKENIZED text is sent (identifiers are vault tokens such as
[MEMBER_ID_1]). The key is read from OPENAI_API_KEY in the git-ignored .env and never logged.

Scope matches the earlier local-LLM experiment: the model fills extraction fields (merged safely over the
offline result, see llm/merge.py). Writing keeps the offline, citation-verified sentence structure, and
query rewriting stays dictionary-based, so citation checks stay mechanical.
"""

from __future__ import annotations

from typing import Any

import httpx

from appeal_core.llm.base import guarded_call, prompt
from appeal_core.llm.merge import merge_model_fields
from appeal_core.llm.offline import offline_extract, offline_rewrite, offline_write
from appeal_core.settings import get_settings


class OpenAINotConfigured(RuntimeError):
    pass


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str | None = None, model: str | None = None, base_url: str | None = None):
        s = get_settings()
        self.api_key = api_key if api_key is not None else s.openai_api_key
        self.model = model or s.openai_model
        self.base_url = (base_url or s.openai_base_url).rstrip("/")
        self.cost_per_1k = s.openai_cost_per_1k_tokens
        if not self.api_key:
            raise OpenAINotConfigured(
                "LLM_PROVIDER=openai but OPENAI_API_KEY is empty. Put the key in .env (git-ignored), or set LLM_PROVIDER=offline."
            )

    def _chat(self, system: str, user: str) -> str:
        r = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            },
            timeout=60,
        )
        if r.status_code >= 400:
            # never echo request headers (they hold the key); the API's error message is enough
            msg = r.json().get("error", {}).get("message", r.text[:200]) if r.headers.get("content-type", "").startswith("application/json") else r.text[:200]
            raise RuntimeError(f"OpenAI API {r.status_code}: {msg}")
        return r.json()["choices"][0]["message"]["content"]

    def extract(self, tokenized_text: str, case_raw_values: list[str]) -> dict[str, Any]:
        p = prompt("intake_extract")

        def call(payload: dict) -> dict:
            base = offline_extract(payload["document"])
            return merge_model_fields(base, self._chat(p["system"], p["user"].format(document=payload["document"])))

        out, _ = guarded_call(self.name, self.model, "intake_extract", {"document": tokenized_text}, case_raw_values, call, cost_per_1k=self.cost_per_1k)
        return out

    def write(self, request: dict[str, Any], case_raw_values: list[str]) -> dict[str, Any]:
        out, _ = guarded_call(self.name, self.model, "writer_letter", request, case_raw_values, offline_write)
        return out

    def rewrite_query(self, query: str, case_raw_values: list[str]) -> list[str]:
        out, _ = guarded_call(self.name, self.model, "query_rewrite", {"query": query}, case_raw_values, lambda p: offline_rewrite(p["query"]))
        return out
