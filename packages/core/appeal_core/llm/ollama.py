"""Optional local LLM provider (Phase B): Ollama on localhost. No key, no cloud.

Uses the same contracts as the offline provider. Every call still goes through `guarded_call`, so the
leak gate runs first. Extraction asks for JSON; if the model's JSON is invalid the provider falls back
to the deterministic offline result for that call (and records nothing as degraded, since output is
schema-identical). Writing keeps the offline sentence structure and citation IDs, so verification stays
mechanical; a model-written variant is a Phase B experiment measured by `make eval`.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from appeal_core.llm.base import ProviderUnavailable, guarded_call, prompt
from appeal_core.llm.offline import offline_extract, offline_rewrite, offline_write


class OllamaNotRunning(RuntimeError):
    pass


LIST_FIELDS = {"denial_codes"}


def _same_shape(v: Any, field: str) -> bool:
    """Accept a model value only if it has the field's type: a list of strings for list fields, else a
    non-empty string. Small models sometimes answer a string field with a list (or the reverse); those
    values are ignored and the deterministic offline value is kept."""
    if field in LIST_FIELDS:
        return isinstance(v, list) and all(isinstance(c, str) for c in v)
    return isinstance(v, str) and bool(v.strip())


class OllamaProvider:
    name = "ollama"

    def __init__(self, host: str | None = None, model: str | None = None):
        self.host = host or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
        self.model = model or os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
        try:
            httpx.get(f"{self.host}/api/tags", timeout=2).raise_for_status()
        except Exception as e:
            raise OllamaNotRunning(
                f"LLM_PROVIDER=ollama but no Ollama server answered at {self.host} ({type(e).__name__}). "
                "Install Ollama, run `ollama pull llama3.2:3b`, or set LLM_PROVIDER=offline."
            ) from e

    def _chat(self, system: str, user: str) -> str:
        r = httpx.post(
            f"{self.host}/api/chat",
            json={"model": self.model, "stream": False, "format": "json", "options": {"temperature": 0}, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["message"]["content"]

    def extract(self, tokenized_text: str, case_raw_values: list[str]) -> dict[str, Any]:
        p = prompt("intake_extract")

        def call(payload: dict) -> dict:
            base = offline_extract(payload["document"])
            try:
                got = json.loads(self._chat(p["system"], p["user"].format(document=payload["document"])))
                for k, v in (got.get("fields") or got).items():
                    if k in base["fields"] and _same_shape(v, k):
                        base["fields"][k]["value"] = [c.strip() for c in v] if isinstance(v, list) else v.strip()
            except Exception:
                pass
            return base

        try:
            out, _ = guarded_call(self.name, self.model, "intake_extract", {"document": tokenized_text}, case_raw_values, call)
        except ProviderUnavailable:
            raise
        return out

    def write(self, request: dict[str, Any], case_raw_values: list[str]) -> dict[str, Any]:
        out, _ = guarded_call(self.name, self.model, "writer_letter", request, case_raw_values, offline_write)
        return out

    def rewrite_query(self, query: str, case_raw_values: list[str]) -> list[str]:
        out, _ = guarded_call(self.name, self.model, "query_rewrite", {"query": query}, case_raw_values, lambda p: offline_rewrite(p["query"]))
        return out
