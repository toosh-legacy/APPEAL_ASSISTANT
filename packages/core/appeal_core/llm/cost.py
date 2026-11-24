"""Cost guard and spend ledger.

LiteLLM prices every call (`response_cost`, from its maintained model price map) and reports cache hits; the
gateway's success callback writes both here. The ledger is one JSON file per session (LLM_SESSION, default the
UTC date) so the hard stop (LLM_BUDGET_USD, default $5) holds across processes during an overnight run.
`CostGuard` is the LangChain callback that refuses a call once the session budget is spent.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

from appeal_core.settings import ROOT, get_settings

_EMPTY = {
    "usd": 0.0,
    "calls": 0,
    "tokens_in": 0,
    "tokens_out": 0,
    "cache_lookups": 0,
    "cache_hits": 0,
    "usd_saved": 0.0,
}


class BudgetExceeded(RuntimeError):
    """Raised before a call when the session budget is spent. Never retried."""


class Ledger:
    def __init__(
        self, session: str | None = None, budget_usd: float | None = None, ledger_dir: Path | None = None
    ):
        s = get_settings()
        self.session = session or s.llm_session or datetime.now(UTC).strftime("%Y-%m-%d")
        self.budget = s.llm_budget_usd if budget_usd is None else budget_usd
        self.path = (ledger_dir or ROOT / "var" / "llm_spend") / f"{self.session}.json"
        self._lock = threading.Lock()

    def read(self) -> dict[str, Any]:
        try:
            return {**_EMPTY, **json.loads(self.path.read_text(encoding="utf-8"))}
        except (OSError, ValueError):
            return {"session": self.session, **_EMPTY}

    @property
    def spent(self) -> float:
        return float(self.read()["usd"])

    def record(
        self,
        usd: float = 0.0,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cache_lookup: bool = False,
        cache_hit: bool = False,
        usd_saved: float = 0.0,
    ) -> None:
        with self._lock:
            d = self.read()
            d["usd"] = round(d["usd"] + usd, 6)
            d["calls"] += 0 if cache_hit else 1
            d["tokens_in"] += tokens_in
            d["tokens_out"] += tokens_out
            d["cache_lookups"] += int(cache_lookup)
            d["cache_hits"] += int(cache_hit)
            d["usd_saved"] = round(d["usd_saved"] + usd_saved, 6)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(d), encoding="utf-8")

    def lookup(self) -> None:
        with self._lock:
            d = self.read()
            d["cache_lookups"] += 1
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(d), encoding="utf-8")

    def check(self) -> None:
        if self.spent >= self.budget:
            raise BudgetExceeded(
                f"LLM budget of ${self.budget:.2f} for session {self.session} is spent (${self.spent:.4f})."
            )

    def summary(self) -> dict[str, Any]:
        d = self.read()
        d["cache_hit_rate"] = round(d["cache_hits"] / d["cache_lookups"], 4) if d["cache_lookups"] else None
        d["budget_usd"] = self.budget
        return d


class CostGuard(BaseCallbackHandler):
    """LangChain callback: checks the session budget before every chat-model call."""

    raise_error = True  # re-raise BudgetExceeded instead of logging it

    def __init__(self, ledger: Ledger):
        self.ledger = ledger

    def on_chat_model_start(self, serialized: dict[str, Any], messages: list, **kw: Any) -> None:
        self.ledger.check()

    def on_llm_start(self, serialized: dict[str, Any], prompts: list[str], **kw: Any) -> None:
        self.ledger.check()


_LEDGER: Ledger | None = None


def get_ledger() -> Ledger:
    global _LEDGER
    if _LEDGER is None:
        _LEDGER = Ledger()
    return _LEDGER
