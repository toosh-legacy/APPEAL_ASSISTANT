"""LiteLLM gateway: the only path from this codebase to a hosted model.

- One `litellm.Router` with a deployment per tier (fast, strong, embed, optional fine-tuned) and a fallback
  model per chat tier.
- Spend limits: LiteLLM `max_budget` per process (LLM_RUN_BUDGET_USD) plus the session ledger (cost.py).
- Caching: a Redis semantic cache (RediSearch vectors) answers near-duplicate query-rewrite prompts; query
  embeddings use an exact Redis cache. Every other call opts out, so letters are never served from cache.
- Every response is priced by LiteLLM and logged to the ledger with cache hits and the cost they saved.
- `store=False` on every OpenAI request: nothing is kept for distillation or evals on OpenAI's side.

LangChain code gets chat models from `get_chat(tier)` (a `ChatLiteLLMRouter`) and embeddings from
`get_embeddings()`. With LLM_PROVIDER=offline the chat model is the deterministic `OfflineChatModel`.
"""

from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel

from appeal_core.llm.cost import CostGuard, get_ledger
from appeal_core.settings import get_settings
from appeal_core.telemetry import get_logger

log = get_logger("gateway")

CHAT_TIERS = ("fast", "strong", "rewrite")
CACHED_TIERS = {"rewrite"}
NO_CACHE = {"cache": {"no-cache": True, "no-store": True}}


class ModelsNotAvailable(RuntimeError):
    pass


def configure_langsmith() -> None:
    """LangSmith tracing only when a key is configured; otherwise make sure it is off."""
    s = get_settings()
    if s.langsmith_api_key:
        os.environ["LANGSMITH_API_KEY"] = s.langsmith_api_key
        os.environ.setdefault("LANGSMITH_TRACING", "true")
        os.environ.setdefault("LANGSMITH_PROJECT", s.langsmith_project)
    else:
        os.environ["LANGSMITH_TRACING"] = "false"


def _model_ids() -> dict[str, str]:
    s = get_settings()
    ids = {
        "fast": s.openai_model_fast,
        "fast-fallback": s.openai_model_fast_fallback,
        "strong": s.openai_model_strong,
        "strong-fallback": s.openai_model_strong_fallback,
        "rewrite": s.openai_model_fast,
        "embed": s.openai_embedding_model,
    }
    if s.openai_fine_tuned_model:
        ids["fast-ft"] = s.openai_fine_tuned_model
    return ids


def _on_success(kwargs: dict[str, Any], response: Any, start: Any, end: Any) -> None:
    import litellm

    usage = getattr(response, "usage", None)
    tin = int(getattr(usage, "prompt_tokens", 0) or 0)
    tout = int(getattr(usage, "completion_tokens", 0) or 0)
    hit = bool(kwargs.get("cache_hit"))
    saved = 0.0
    if hit:
        try:
            # cache hits report the tier alias ("rewrite"), not the model: price them as the tier's model
            name = str(kwargs.get("model", "")).removeprefix("openai/")
            mid = _model_ids().get(name, name)
            a, b = litellm.cost_per_token(model=mid, prompt_tokens=tin, completion_tokens=tout)
            saved = a + b
        except Exception:
            saved = 0.0
    get_ledger().record(
        usd=0.0 if hit else float(kwargs.get("response_cost") or 0.0),
        tokens_in=tin,
        tokens_out=tout,
        cache_hit=hit,
        usd_saved=saved,
    )


def _setup_cache() -> str:
    import litellm
    from litellm.caching.caching import Cache
    from litellm.types.caching import LiteLLMCacheType

    s = get_settings()
    if s.semantic_cache:
        try:
            litellm.cache = Cache(
                type=LiteLLMCacheType.REDIS_SEMANTIC,
                redis_url=s.redis_url,
                similarity_threshold=s.semantic_cache_threshold,
                redis_semantic_cache_embedding_model=f"openai/{s.openai_embedding_model}",
                supported_call_types=["completion", "acompletion"],
            )
            return "redis-semantic"
        except Exception as e:  # Redis without RediSearch, or not running
            log.warning(
                "semantic cache unavailable, using in-memory exact cache", extra={"error": type(e).__name__}
            )
    litellm.cache = Cache(type=LiteLLMCacheType.LOCAL, supported_call_types=["completion", "acompletion"])
    return "local"


@lru_cache
def router():
    import litellm
    from litellm import Router

    s = get_settings()
    os.environ["OPENAI_API_KEY"] = s.openai_api_key  # LiteLLM's semantic-cache embedder reads it from the env
    litellm.drop_params = True
    litellm.success_callback = [_on_success]
    litellm.max_budget = s.llm_run_budget_usd
    cache_kind = _setup_cache()
    chat = {"store": False}
    model_list = [
        {
            "model_name": name,
            "litellm_params": {
                "model": f"openai/{mid}",
                "api_key": s.openai_api_key,
                **({} if name == "embed" else chat),
            },
        }
        for name, mid in _model_ids().items()
    ]
    r = Router(
        model_list=model_list,
        fallbacks=[
            {"fast": ["fast-fallback"]},
            {"rewrite": ["fast-fallback"]},
            {"strong": ["strong-fallback"]},
            {"fast-ft": ["fast"]},
        ],
        cache_responses=True,
        num_retries=2,
        timeout=60,
    )
    log.info("llm gateway ready", extra={"cache": cache_kind, "tiers": sorted(_model_ids())})
    return r


@lru_cache
def get_chat(tier: str) -> BaseChatModel:
    s = get_settings()
    if s.llm_provider == "offline":
        from appeal_core.llm.offline_chat import OfflineChatModel

        return OfflineChatModel()
    if s.llm_provider != "openai":
        raise ValueError(f"unknown LLM_PROVIDER={s.llm_provider}")
    if not s.openai_api_key:
        raise ModelsNotAvailable(
            "LLM_PROVIDER=openai but OPENAI_API_KEY is empty. Put the key in .env (git-ignored), or set LLM_PROVIDER=offline."
        )
    from langchain_litellm import ChatLiteLLMRouter

    configure_langsmith()
    kwargs = {} if tier in CACHED_TIERS else NO_CACHE
    return ChatLiteLLMRouter(
        router=router(),
        model_name=tier,
        temperature=0,
        model_kwargs=kwargs,
        callbacks=[CostGuard(get_ledger())],
    )


def model_id(tier: str) -> str:
    s = get_settings()
    return "offline-rules-v1" if s.llm_provider == "offline" else _model_ids().get(tier, tier)


def verify_models() -> dict[str, str]:
    """Startup check: every configured model ID exists on the account (OpenAI SDK `client.models.list()`)."""
    s = get_settings()
    if s.llm_provider != "openai":
        return {}
    from openai import OpenAI

    available = {m.id for m in OpenAI(api_key=s.openai_api_key).models.list()}
    ids = _model_ids()
    missing = {k: v for k, v in ids.items() if v not in available}
    if missing:
        raise ModelsNotAvailable(
            f"model IDs not available on this OpenAI account: {missing}. Fix OPENAI_MODEL_* in .env."
        )
    return ids


def moderate(text: str) -> list[str]:
    """OpenAI Moderation (omni-moderation-latest) via LiteLLM. Returns the flagged categories."""
    s = get_settings()
    if s.llm_provider != "openai":
        return []
    import litellm

    get_ledger().check()
    res = litellm.moderation(input=text, model="omni-moderation-latest", api_key=s.openai_api_key)
    r = res.results[0]
    raw = r.categories or {}
    cats: dict[str, Any] = raw if isinstance(raw, dict) else raw.model_dump()
    return sorted(k for k, v in cats.items() if v)


class GatewayEmbeddings(Embeddings):
    """OpenAI embeddings through the gateway. Query embeddings hit an exact Redis cache first."""

    def __init__(self) -> None:
        self.model = get_settings().openai_embedding_model
        self._redis = None

    def _r(self):
        if self._redis is None:
            import redis

            self._redis = redis.Redis.from_url(get_settings().redis_url)
        return self._redis

    def _embed(self, texts: list[str], cache: bool) -> list[list[float]]:
        get_ledger().check()
        res = router().embedding(model="embed", input=texts, **({} if cache else NO_CACHE))
        return [d["embedding"] for d in res.data]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), 256):
            out += self._embed(texts[i : i + 256], cache=False)
        return out

    def embed_query(self, text: str) -> list[float]:
        key = f"emb:{self.model}:{hashlib.sha256(text.encode()).hexdigest()}"
        try:
            hit = self._r().get(key)
        except Exception:
            hit = None
        if hit:
            import litellm

            a, _ = litellm.cost_per_token(
                model=self.model, prompt_tokens=max(1, len(text) // 4), completion_tokens=0
            )
            get_ledger().record(cache_lookup=True, cache_hit=True, usd_saved=a)
            return json.loads(hit)
        vec = self._embed([text], cache=False)[0]
        get_ledger().record(cache_lookup=True)
        try:
            self._r().set(key, json.dumps(vec), ex=30 * 86400)
        except Exception:
            pass
        return vec


def get_embeddings() -> Embeddings:
    s = get_settings()
    if s.llm_provider == "openai" and s.embedder == "openai":
        return GatewayEmbeddings()
    from langchain_core.embeddings import DeterministicFakeEmbedding

    return DeterministicFakeEmbedding(size=1536)
