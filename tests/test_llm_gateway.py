"""LLM layer without network or key: LangChain fake chat models stand in for the hosted model."""

from __future__ import annotations

from typing import Any

import pytest
from appeal_core.llm import chat as chat_mod
from appeal_core.llm.base import guarded_call
from appeal_core.llm.contracts import CategoryOut, ExtractionOut
from appeal_core.llm.cost import BudgetExceeded, CostGuard, Ledger
from appeal_core.llm.offline import offline_extract
from appeal_core.llm.offline_chat import OfflineChatModel
from appeal_core.privacy.leak_gate import LeakBlocked
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda

LETTER = """Example Health Plan
Notice date: March 3, 2025
Member ID: [MEMBER_ID_1]
Service: MRI of the brain
Reason for denial: The service is not medically necessary.
"""


class FakeStructuredChat(BaseChatModel):
    """Returns a fixed structured answer and records what the chain sent it."""

    answer: Any = None
    seen: list = []

    @property
    def _llm_type(self) -> str:
        return "fake-structured"

    def _generate(self, messages, stop=None, run_manager=None, **kw) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="{}"))])

    def with_structured_output(self, schema, **kw):  # type: ignore[override]
        def run(inp):
            self.seen.append(inp.to_messages())
            return self.answer

        return RunnableLambda(run)


def _use(monkeypatch, model: BaseChatModel) -> None:
    monkeypatch.setattr(chat_mod, "get_chat", lambda tier: model)


def test_offline_chat_model_runs_the_same_chain_as_production():
    out = (
        chat_mod.template("intake_extract") | OfflineChatModel().with_structured_output(ExtractionOut)
    ).invoke({"document": LETTER})
    want = {k: v["value"] for k, v in offline_extract(LETTER)["fields"].items()}
    assert (
        out.insurer == want["insurer"]
        and out.service == want["service"]
        and out.denial_reason == want["denial_reason"]
    )


def test_model_values_merge_only_when_grounded(monkeypatch):
    answer = ExtractionOut(
        insurer="Example Health Plan", plan_type=None, state="CA", claim_number=None, member_id="[MEMBER_ID_1]",
        service="MRI of the brain", date_of_service=None, notice_date="2025-03-03",
        denial_reason="Your plan thinks it is experimental.", denial_codes=["CO-50"],
    )  # fmt: skip
    _use(monkeypatch, FakeStructuredChat(answer=answer))
    f = chat_mod.LLMProvider().extract(LETTER, [])["fields"]
    assert f["state"]["value"] == "CA" and f["denial_codes"]["value"] == ["CO-50"]
    assert f["denial_reason"]["value"] == "The service is not medically necessary."  # paraphrase rejected


def test_only_tokenized_text_reaches_the_model(monkeypatch):
    fake = FakeStructuredChat(
        answer=CategoryOut(category="medical_necessity", confidence=0.9, rationale="x"), seen=[]
    )
    _use(monkeypatch, fake)
    chat_mod.LLMProvider().classify("not medically necessary for [MEMBER_ID_1]", [], None, ["ZZTEST123456"])
    assert "[MEMBER_ID_1]" in fake.seen[0][-1].content and "ZZTEST" not in fake.seen[0][-1].content


def test_leak_gate_blocks_before_the_chain_runs(monkeypatch):
    fake = FakeStructuredChat(answer=None, seen=[])
    _use(monkeypatch, fake)
    with pytest.raises(LeakBlocked):
        chat_mod.LLMProvider().extract("Member ID ZZTEST123456 was denied.", ["ZZTEST123456"])
    assert fake.seen == []


def test_cost_guard_stops_hard_at_the_budget(tmp_path):
    led = Ledger(session="t", budget_usd=0.01, ledger_dir=tmp_path)
    guard = CostGuard(led)
    guard.on_chat_model_start({}, [])  # under budget: fine
    led.record(usd=0.02, tokens_in=100, tokens_out=10)
    with pytest.raises(BudgetExceeded):
        guard.on_chat_model_start({}, [])
    assert Ledger(session="t", budget_usd=0.01, ledger_dir=tmp_path).spent == pytest.approx(0.02)  # persisted


def test_budget_errors_are_not_retried():
    calls = {"n": 0}

    def fn(_):
        calls["n"] += 1
        raise BudgetExceeded("spent")

    with pytest.raises(BudgetExceeded):
        guarded_call("openai", "m", "intake_extract", {"document": "x"}, [], fn, base_delay=0)
    assert calls["n"] == 1


def test_ledger_tracks_cache_hits_and_savings(tmp_path, monkeypatch):
    from appeal_core.llm import cost, gateway

    led = Ledger(session="c", ledger_dir=tmp_path)
    monkeypatch.setattr(cost, "_LEDGER", led)
    monkeypatch.setattr(gateway, "get_ledger", lambda: led)

    class U:
        prompt_tokens, completion_tokens = 1000, 100

    class R:
        usage = U()

    led.lookup()
    led.lookup()
    gateway._on_success(
        {
            "model": "gpt-4.1-mini",
            "response_cost": 0.0006,
            "litellm_params": {"metadata": {"model_group": "rewrite"}},
        },
        R(),
        None,
        None,
    )
    gateway._on_success(
        {
            "model": "gpt-4.1-mini",
            "cache_hit": True,
            "litellm_params": {"metadata": {"model_group": "rewrite"}},
        },
        R(),
        None,
        None,
    )
    s = led.summary()
    assert (
        s["calls"] == 1
        and s["cache_lookups"] == 2
        and s["cache_hit_rate"] == 0.5
        and s["usd"] == pytest.approx(0.0006)
        and s["usd_saved"] > 0
    )


def test_openai_without_a_key_is_a_clear_error(monkeypatch):
    from appeal_core.llm import gateway
    from appeal_core.settings import get_settings

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    gateway.get_chat.cache_clear()
    try:
        with pytest.raises(gateway.ModelsNotAvailable) as e:
            gateway.get_chat("fast")
        assert "OPENAI_API_KEY" in str(e.value)
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        gateway.get_chat.cache_clear()


def test_startup_check_names_missing_model_ids(monkeypatch):
    from appeal_core.llm import gateway
    from appeal_core.settings import get_settings

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key-000000")
    monkeypatch.setenv("OPENAI_MODEL_STRONG", "no-such-model")
    get_settings.cache_clear()

    class M:
        def __init__(self, i):
            self.id = i

    class Client:
        def __init__(self, api_key):
            self.models = self

        def list(self):
            return [M(i) for i in ("gpt-4.1-mini", "gpt-4o-mini", "gpt-4o", "text-embedding-3-small")]

    import openai

    monkeypatch.setattr(openai, "OpenAI", Client)
    try:
        with pytest.raises(gateway.ModelsNotAvailable) as e:
            gateway.verify_models()
        assert "no-such-model" in str(e.value)
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_langsmith_tracing_is_off_without_a_key(monkeypatch):
    import os

    from appeal_core.llm.gateway import configure_langsmith

    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    configure_langsmith()
    assert os.environ["LANGSMITH_TRACING"] == "false"


def test_log_scrubber_redacts_api_keys():
    from appeal_core.telemetry import scrub

    key = "sk-test-not-a-real-key-000000"
    out = scrub({"msg": f"call failed with key {key}", "h": "Bearer abcdefghijklmnopqrstuvwxyz123"})
    assert key not in str(out) and "abcdefghijklmnop" not in str(out)
