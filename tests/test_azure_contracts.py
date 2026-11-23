"""Azure adapter contract tests. Skipped unless the adapter's env vars are set (Phase C).
Without credentials, selecting an Azure backend must give a clear NotConfigured error, not a crash."""

import os

import pytest
from appeal_core.adapters import azure as A

ADAPTERS = [
    (A.ServiceBusJobQueue, "AZURE_SERVICEBUS_NAMESPACE"),
    (A.AzureBlobStore, "AZURE_STORAGE_ACCOUNT_URL"),
    (A.AzureOpenAIProvider, "AZURE_OPENAI_ENDPOINT"),
    (A.AzureOpenAIEmbedder, "AZURE_OPENAI_ENDPOINT"),
    (A.AzureSearchRetriever, "AZURE_SEARCH_ENDPOINT"),
    (A.AzureLanguagePIIDetector, "AZURE_LANGUAGE_ENDPOINT"),
    (A.PromptShieldsDetector, "AZURE_CONTENT_SAFETY_ENDPOINT"),
    (A.DocumentIntelligenceExtractor, "AZURE_DOCINTEL_ENDPOINT"),
    (A.AzureMLModelRegistry, "AZURE_ML_ENDPOINT"),
    (A.KeyVaultSettings, "AZURE_KEYVAULT_URL"),
]


@pytest.mark.parametrize("cls,var", ADAPTERS)
def test_not_configured_is_clear(cls, var):
    if os.environ.get(var):
        pytest.skip("configured; see the contract tests")
    with pytest.raises(A.NotConfigured) as e:
        cls()
    assert var in str(e.value)


@pytest.mark.parametrize(
    "env,factory",
    [
        ({"QUEUE_BACKEND": "servicebus"}, "get_queue"),
        ({"LLM_PROVIDER": "azure_openai"}, "get_llm"),
        ({"INJECTION_BACKEND": "azure"}, "get_injection_detector"),
        ({"OCR_BACKEND": "azure"}, "get_text_extractor"),
    ],
)
def test_switching_backend_without_credentials(monkeypatch, env, factory):
    from appeal_core import adapters
    from appeal_core.settings import get_settings

    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    try:
        with pytest.raises(A.NotConfigured):
            getattr(adapters, factory)()
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


@pytest.mark.azure
@pytest.mark.skipif(not os.environ.get("AZURE_OPENAI_ENDPOINT"), reason="Azure OpenAI not configured (Phase C)")
def test_azure_openai_contract():
    assert A.AzureOpenAIProvider() is not None


def test_ollama_without_server_gives_clear_error(monkeypatch):
    from appeal_core.llm.ollama import OllamaNotRunning, OllamaProvider

    with pytest.raises(OllamaNotRunning) as e:
        OllamaProvider(host="http://127.0.0.1:9")
    assert "LLM_PROVIDER=offline" in str(e.value)


def test_ollama_ignores_values_with_the_wrong_shape():
    from appeal_core.llm.ollama import _same_shape

    assert _same_shape(["CO-50"], "denial_codes") and not _same_shape("CO-50", "denial_codes")
    assert _same_shape("MRI", "service") and not _same_shape(["MRI"], "service") and not _same_shape("  ", "service")
    assert not _same_shape([1, 2], "denial_codes")
