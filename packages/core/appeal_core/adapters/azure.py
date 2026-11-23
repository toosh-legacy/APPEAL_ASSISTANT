"""Azure adapters (Phase C). In Phases A/B they only validate configuration and raise NotConfigured with a
clear message; nothing here calls Azure. Each names the env vars it will need."""

from __future__ import annotations

from appeal_core.settings import get_settings


class NotConfigured(RuntimeError):
    pass


class _AzureAdapter:
    service = "Azure service"
    env_vars: tuple[str, ...] = ()
    bicep_module = ""

    def __init__(self, *args, **kwargs):
        s = get_settings()
        missing = [v for v in self.env_vars if not getattr(s, v.lower(), "")]
        if missing:
            raise NotConfigured(
                f"{self.service} adapter selected but not configured: set {', '.join(missing)} "
                f"(deployed by infra/{self.bicep_module}). Use the local adapter in Phases A/B."
            )
        raise NotConfigured(f"{self.service} adapter is a Phase C stub; implementation pending (see infra/README.md)")


class ServiceBusJobQueue(_AzureAdapter):
    service, env_vars, bicep_module = "Azure Service Bus", ("AZURE_SERVICEBUS_NAMESPACE",), "modules/servicebus.bicep"


class AzureBlobStore(_AzureAdapter):
    service, env_vars, bicep_module = "Azure Blob Storage", ("AZURE_STORAGE_ACCOUNT_URL",), "modules/storage.bicep"


class AzureRedisProgressBus(_AzureAdapter):
    service, env_vars, bicep_module = "Azure Managed Redis", ("REDIS_URL",), "modules/redis.bicep"


class AzureOpenAIProvider(_AzureAdapter):
    service, env_vars, bicep_module = "Azure OpenAI", ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT"), "modules/openai.bicep"


class AzureOpenAIEmbedder(_AzureAdapter):
    service, env_vars, bicep_module = "Azure OpenAI embeddings", ("AZURE_OPENAI_ENDPOINT",), "modules/openai.bicep"


class AzureSearchRetriever(_AzureAdapter):
    service, env_vars, bicep_module = "Azure AI Search", ("AZURE_SEARCH_ENDPOINT",), "modules/search.bicep"


class AzureLanguagePIIDetector(_AzureAdapter):
    service, env_vars, bicep_module = "Azure AI Language PII", ("AZURE_LANGUAGE_ENDPOINT",), "modules/language.bicep"


class PromptShieldsDetector(_AzureAdapter):
    service, env_vars, bicep_module = "Content Safety Prompt Shields", ("AZURE_CONTENT_SAFETY_ENDPOINT",), "modules/contentsafety.bicep"


class DocumentIntelligenceExtractor(_AzureAdapter):
    service, env_vars, bicep_module = "Document Intelligence", ("AZURE_DOCINTEL_ENDPOINT",), "modules/docintel.bicep"


class AzureMLModelRegistry(_AzureAdapter):
    service, env_vars, bicep_module = "Azure ML", ("AZURE_ML_ENDPOINT",), "modules/ml.bicep"


class KeyVaultSettings(_AzureAdapter):
    service, env_vars, bicep_module = "Key Vault", ("AZURE_KEYVAULT_URL",), "modules/keyvault.bicep"
