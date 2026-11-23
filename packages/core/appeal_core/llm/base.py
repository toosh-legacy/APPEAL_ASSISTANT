"""Provider call wrapper: leak gate (fail closed) -> retries with backoff + jitter -> circuit breaker ->
call log (prompt id/version, provider, model, tokens, latency, cost). Captured inputs feed the privacy eval."""

from __future__ import annotations

import json
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from appeal_core.privacy.leak_gate import check_payload
from appeal_core.settings import ROOT

PROMPTS = ROOT / "packages" / "prompts"


@lru_cache
def prompt(prompt_id: str) -> dict[str, Any]:
    return yaml.safe_load((PROMPTS / f"{prompt_id}.yaml").read_text(encoding="utf-8"))


def prompt_versions() -> dict[str, str]:
    return {p.stem: yaml.safe_load(p.read_text(encoding="utf-8"))["version"] for p in sorted(Path(PROMPTS).glob("*.yaml"))}


class ProviderUnavailable(Exception):
    pass


@dataclass
class CallRecord:
    prompt_id: str
    prompt_version: str
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    cost_usd: float


@dataclass
class CallLog:
    records: list[CallRecord] = field(default_factory=list)
    captured_inputs: list[str] = field(default_factory=list)  # what the provider actually received


CALL_LOG = CallLog()


class CircuitBreaker:
    def __init__(self, threshold: int = 3, cooldown_s: float = 30.0):
        self.failures = 0
        self.threshold = threshold
        self.cooldown_s = cooldown_s
        self.opened_at: float | None = None

    @property
    def open(self) -> bool:
        if self.opened_at is None:
            return False
        if time.time() - self.opened_at > self.cooldown_s:
            self.opened_at = None
            self.failures = 0
            return False
        return True

    def record(self, ok: bool) -> None:
        if ok:
            self.failures = 0
            return
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = time.time()


BREAKERS: dict[str, CircuitBreaker] = {}


def _tok(s: str) -> int:
    return max(1, len(s) // 4)


def guarded_call(
    provider: str,
    model: str,
    prompt_id: str,
    payload: dict[str, Any],
    raw_values: list[str],
    fn: Callable[[dict[str, Any]], Any],
    retries: int = 3,
    base_delay: float = 0.2,
    cost_per_1k: float = 0.0,
) -> tuple[Any, CallRecord]:
    """Every provider call goes through here. The leak gate runs first and raises LeakBlocked (fail closed)."""
    check_payload(payload, raw_values)
    serialized = json.dumps(payload, ensure_ascii=False, default=str)
    CALL_LOG.captured_inputs.append(serialized)
    br = BREAKERS.setdefault(provider, CircuitBreaker())
    if br.open:
        raise ProviderUnavailable(f"circuit open for {provider}")
    p = prompt(prompt_id)
    last: Exception | None = None
    for attempt in range(retries):
        t0 = time.perf_counter()
        try:
            out = fn(payload)
            br.record(True)
            out_s = json.dumps(out, default=str) if not isinstance(out, str) else out
            rec = CallRecord(
                prompt_id=prompt_id,
                prompt_version=p["version"],
                provider=provider,
                model=model,
                tokens_in=_tok(serialized),
                tokens_out=_tok(out_s),
                latency_ms=int((time.perf_counter() - t0) * 1000),
                cost_usd=round((_tok(serialized) + _tok(out_s)) / 1000 * cost_per_1k, 6),
            )
            CALL_LOG.records.append(rec)
            return out, rec
        except Exception as e:  # provider error
            last = e
            br.record(False)
            if br.open:
                break
            time.sleep(base_delay * (2**attempt) + random.random() * base_delay)
    raise ProviderUnavailable(f"{provider} failed after retries: {last}")
