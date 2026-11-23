"""Application settings. Environment variables only (documented in .env.example)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore")

    app_env: str = "local"
    database_url: str = "postgresql+psycopg://appeal:appeal_local_only@127.0.0.1:55432/appeal"
    test_database_url: str = "postgresql+psycopg://appeal:appeal_local_only@127.0.0.1:55432/appeal_test"

    queue_backend: str = "postgres"
    blob_backend: str = "azurite"
    progress_backend: str = "redis"
    llm_provider: str = "offline"
    embedder: str = "minilm"
    retriever_backend: str = "postgres"
    reranker: str = "crossencoder"  # crossencoder | none (CI: none, avoids the model download)
    pii_backend: str = "local"
    injection_backend: str = "local"
    ocr_backend: str = "local"
    model_registry: str = "local"
    telemetry_exporter: str = "console"

    redis_url: str = "redis://127.0.0.1:56379/0"
    blob_connection_string: str = ""
    blob_container: str = "uploads"

    worker_mode: str = "separate"
    master_key: str = ""
    case_token_secret: str = "dev-only-insecure"
    admin_token: str = "dev-admin"

    imr_source: str = "real"
    feature_insurer_insights: bool = False
    web_origin: str = "http://localhost:3100"

    max_revisions: int = 2
    classifier_threshold: float = 0.6
    job_max_attempts: int = 5

    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = ""
    azure_search_endpoint: str = ""
    azure_servicebus_namespace: str = ""
    azure_storage_account_url: str = ""
    azure_language_endpoint: str = ""
    azure_content_safety_endpoint: str = ""
    azure_docintel_endpoint: str = ""
    azure_ml_endpoint: str = ""
    azure_keyvault_url: str = ""

    @property
    def root(self) -> Path:
        return ROOT


@lru_cache
def get_settings() -> Settings:
    return Settings()
