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
    llm_provider: str = "offline"  # offline (LangChain fake chat model, tests/CI) | openai (via the LiteLLM gateway)
    openai_api_key: str = ""  # from the git-ignored .env only
    # model tiers (IDs checked against the account at startup); each has a fallback the gateway switches to
    openai_model_fast: str = "gpt-4.1-mini"  # extraction, classification, query rewriting
    openai_model_fast_fallback: str = "gpt-4o-mini"
    openai_model_strong: str = "gpt-4.1"  # writer, reviewer, eval judge
    openai_model_strong_fallback: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_fine_tuned_model: str = ""  # set after `python -m appeal_evals.finetune` to serve the fine-tuned cheap model
    llm_budget_usd: float = 5.0  # hard stop per session (LLM_SESSION, default the UTC date)
    llm_run_budget_usd: float = 2.0  # hard stop per process (LiteLLM max_budget)
    llm_session: str = ""
    semantic_cache: bool = True  # LiteLLM redis-semantic cache for query-rewrite calls; exact cache for query embeddings
    semantic_cache_threshold: float = 0.985  # 0.92 let a different topic hit (the shared system prompt dominates similarity)
    langsmith_api_key: str = ""  # LangSmith tracing only when set; OpenTelemetry always runs
    langsmith_project: str = "appeal-assistant"
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
