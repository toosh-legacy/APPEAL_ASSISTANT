"""Adapter factories. The adapter is chosen by environment variables; callers never import adapters directly."""

from __future__ import annotations

from functools import lru_cache

from appeal_core.settings import get_settings


def get_queue():
    b = get_settings().queue_backend
    if b == "postgres":
        from appeal_core.adapters.queue_postgres import PostgresJobQueue

        return PostgresJobQueue()
    if b == "servicebus":
        from appeal_core.adapters.azure import ServiceBusJobQueue

        return ServiceBusJobQueue()
    raise ValueError(f"unknown QUEUE_BACKEND={b}")


@lru_cache
def get_blob_store():
    b = get_settings().blob_backend
    if b == "azurite":
        from appeal_core.adapters.blob_azurite import AzuriteBlobStore

        return AzuriteBlobStore()
    if b == "azure":
        from appeal_core.adapters.azure import AzureBlobStore

        return AzureBlobStore()
    raise ValueError(f"unknown BLOB_BACKEND={b}")


_bus = None


def get_progress_bus():
    global _bus
    if _bus is not None:
        return _bus
    s = get_settings()
    if s.progress_backend == "redis":
        from appeal_core.adapters.progress import RedisProgressBus

        _bus = RedisProgressBus(s.redis_url)
    elif s.progress_backend == "memory":
        from appeal_core.adapters.progress import MemoryProgressBus

        _bus = MemoryProgressBus()
    elif s.progress_backend == "azure":
        from appeal_core.adapters.azure import AzureRedisProgressBus

        _bus = AzureRedisProgressBus()
    else:
        raise ValueError(f"unknown PROGRESS_BACKEND={s.progress_backend}")
    return _bus


def set_progress_bus(bus) -> None:
    global _bus
    _bus = bus


def get_llm():
    p = get_settings().llm_provider
    if p == "offline":
        from appeal_core.llm.offline import OfflineProvider

        return OfflineProvider()
    if p == "openai":
        from appeal_core.llm.openai_provider import OpenAIProvider

        return OpenAIProvider()
    if p == "ollama":
        from appeal_core.llm.ollama import OllamaProvider

        return OllamaProvider()
    if p == "azure_openai":
        from appeal_core.adapters.azure import AzureOpenAIProvider

        return AzureOpenAIProvider()
    raise ValueError(f"unknown LLM_PROVIDER={p}")


def get_injection_detector():
    b = get_settings().injection_backend
    if b == "local":
        from appeal_core.privacy.injection import HeuristicInjectionDetector

        return HeuristicInjectionDetector()
    if b == "azure":
        from appeal_core.adapters.azure import PromptShieldsDetector

        return PromptShieldsDetector()
    raise ValueError(f"unknown INJECTION_BACKEND={b}")


def get_text_extractor():
    b = get_settings().ocr_backend
    if b == "local":
        from appeal_core.extract_text import PypdfTextExtractor

        return PypdfTextExtractor()
    if b == "azure":
        from appeal_core.adapters.azure import DocumentIntelligenceExtractor

        return DocumentIntelligenceExtractor()
    raise ValueError(f"unknown OCR_BACKEND={b}")
