"""OpenAI provider without network or key: HTTP is mocked, so these tests cost nothing."""

import json

import httpx
import pytest
from appeal_core.llm import openai_provider as op
from appeal_core.llm.merge import merge_model_fields
from appeal_core.llm.offline import offline_extract
from appeal_core.privacy.leak_gate import LeakBlocked

LETTER = """Example Health Plan
Notice date: March 3, 2025
Member ID: [MEMBER_ID_1]
Reason for denial: The service is not medically necessary.
"""
KEY = "sk-test-not-a-real-key-000000"


def _fake_post(answer: dict | str, calls: list, status: int = 200):
    def post(url, headers=None, json=None, timeout=None):
        calls.append({"url": url, "headers": headers, "json": json})
        content = answer if isinstance(answer, str) else __import__("json").dumps(answer)
        body = {"choices": [{"message": {"content": content}}]} if status < 400 else {"error": {"message": "Incorrect API key provided"}}
        return httpx.Response(status, json=body, request=httpx.Request("POST", url))

    return post


def test_missing_key_gives_a_clear_error():
    with pytest.raises(op.OpenAINotConfigured) as e:
        op.OpenAIProvider(api_key="")
    assert "OPENAI_API_KEY" in str(e.value) and "LLM_PROVIDER=offline" in str(e.value)


def test_model_values_are_merged_over_offline(monkeypatch):
    calls: list = []
    monkeypatch.setattr(op.httpx, "post", _fake_post({"service": "MRI of the brain", "state": "CA", "denial_codes": ["CO-50"]}, calls))
    out = op.OpenAIProvider(api_key=KEY, model="test-model").extract(LETTER, [])
    f = out["fields"]
    assert f["service"]["value"] == "MRI of the brain" and f["state"]["value"] == "CA" and f["denial_codes"]["value"] == ["CO-50"]
    assert f["insurer"]["value"] == "Example Health Plan"  # offline value kept where the model said nothing
    assert calls[0]["json"]["model"] == "test-model" and calls[0]["json"]["response_format"] == {"type": "json_object"}
    assert "[MEMBER_ID_1]" in calls[0]["json"]["messages"][1]["content"]  # only tokenized text is sent


def test_wrong_shapes_and_bad_json_never_make_extraction_worse():
    base = offline_extract(LETTER)
    want = json.loads(json.dumps(base))
    assert merge_model_fields(json.loads(json.dumps(base)), "not json") == want
    out = merge_model_fields(json.loads(json.dumps(base)), json.dumps({"insurer": ["A", "B"], "denial_codes": "CO-50", "notice_date": "  "}))
    assert out["fields"]["insurer"]["value"] == want["fields"]["insurer"]["value"]
    assert out["fields"]["denial_codes"]["value"] == want["fields"]["denial_codes"]["value"]
    assert out["fields"]["notice_date"]["value"] == want["fields"]["notice_date"]["value"]


def test_leak_gate_blocks_before_anything_is_sent(monkeypatch):
    calls: list = []
    monkeypatch.setattr(op.httpx, "post", _fake_post({}, calls))
    with pytest.raises(LeakBlocked):
        op.OpenAIProvider(api_key=KEY).extract("Member ID ZZTEST123456 was denied.", ["ZZTEST123456"])
    assert calls == []


def test_api_errors_never_include_the_key(monkeypatch):
    calls: list = []
    monkeypatch.setattr(op.httpx, "post", _fake_post({}, calls, status=401))
    p = op.OpenAIProvider(api_key=KEY)
    with pytest.raises(Exception) as e:
        p._chat("s", "u")
    assert "401" in str(e.value) and KEY not in str(e.value)


def test_factory_selects_openai(monkeypatch):
    from appeal_core import adapters
    from appeal_core.settings import get_settings

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    get_settings.cache_clear()
    try:
        assert isinstance(adapters.get_llm(), op.OpenAIProvider)
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_log_scrubber_redacts_api_keys():
    from appeal_core.telemetry import scrub

    out = scrub({"msg": f"call failed with key {KEY}", "h": "Bearer abcdefghijklmnopqrstuvwxyz123"})
    assert KEY not in str(out) and "abcdefghijklmnop" not in str(out)
