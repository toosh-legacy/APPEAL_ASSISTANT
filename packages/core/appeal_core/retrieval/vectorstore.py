"""Vector stores for the OpenAI-embedding side of hybrid search (text-embedding-3-small, 1536-d).

Full mode: langchain-postgres `PGVector`, one collection per corpus (kb rules, IMR precedents), with chunk
metadata in JSONB for filtering and an HNSW cosine index. Lite mode: a numpy matrix per collection behind
the same two methods. Embeddings come from the LiteLLM gateway (`gateway.get_embeddings`), so indexing and
query calls are priced, budget-capped and (for queries) cached like every other model call.

The local MiniLM vectors in kb_chunk/precedent_chunk stay for offline runs (tests, CI, `make eval`).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from langchain_core.embeddings import Embeddings

from appeal_core.settings import ROOT, get_settings

DIM = 1536
COLLECTIONS = {"kb_chunk": "kb_rules_openai", "precedent_chunk": "precedents_openai"}


class PGVectorStore:
    def __init__(self, collection: str, embeddings: Embeddings, url: str | None = None):
        from langchain_postgres import PGVector

        self.collection = collection
        self.url = url or get_settings().database_url
        self.store = PGVector(embeddings=embeddings, connection=self.url, collection_name=collection, embedding_length=DIM, use_jsonb=True)

    def add(self, ids: list[str], vectors: list[list[float]], texts: list[str], metadatas: list[dict[str, Any]]) -> None:
        self.store.add_embeddings(texts=texts, embeddings=vectors, metadatas=metadatas, ids=ids)

    def ensure_index(self) -> None:
        from sqlalchemy import create_engine, text

        eng = create_engine(self.url)
        with eng.begin() as c:
            c.execute(text("CREATE INDEX IF NOT EXISTS ix_lc_embedding_hnsw ON langchain_pg_embedding USING hnsw (embedding vector_cosine_ops)"))

    def existing_ids(self) -> set[str]:
        from sqlalchemy import create_engine, text

        eng = create_engine(self.url)
        sql = text("SELECT e.id FROM langchain_pg_embedding e JOIN langchain_pg_collection c ON c.uuid = e.collection_id WHERE c.name = :n")
        with eng.connect() as c:
            return {r[0] for r in c.execute(sql, {"n": self.collection})}

    def search(self, vector: list[float], k: int, filter: dict[str, Any] | None = None) -> list[tuple[str, float]]:
        docs = self.store.similarity_search_with_score_by_vector(vector, k=k, filter=filter or None)
        return [(str(d.id), float(s)) for d, s in docs]


class NumpyVectorStore:
    """Lite mode: exact cosine search over an in-memory matrix, saved to var/vectors/<collection>.npz."""

    def __init__(self, collection: str, root: Path | None = None):
        self.path = (root or ROOT / "var" / "vectors") / f"{collection}.npz"
        self.ids: list[str] = []
        self.meta: list[dict[str, Any]] = []
        self.mat = np.zeros((0, DIM), dtype=np.float32)
        if self.path.exists():
            z = np.load(self.path, allow_pickle=False)
            self.mat, self.ids, self.meta = z["mat"], list(z["ids"]), [json.loads(m) for m in z["meta"]]

    def add(self, ids: list[str], vectors: list[list[float]], texts: list[str], metadatas: list[dict[str, Any]]) -> None:
        v = np.asarray(vectors, dtype=np.float32)
        v /= np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)
        self.mat = np.vstack([self.mat, v])
        self.ids += ids
        self.meta += metadatas
        self.path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(self.path, mat=self.mat, ids=np.array(self.ids), meta=np.array([json.dumps(m) for m in self.meta]))

    def ensure_index(self) -> None:
        return None

    def existing_ids(self) -> set[str]:
        return set(self.ids)

    def search(self, vector: list[float], k: int, filter: dict[str, Any] | None = None) -> list[tuple[str, float]]:
        if not self.ids:
            return []
        q = np.asarray(vector, dtype=np.float32)
        q /= max(float(np.linalg.norm(q)), 1e-9)
        sims = self.mat @ q
        if filter:
            keep = np.array([all(m.get(f) == cond.get("$eq") for f, cond in filter.items()) for m in self.meta])
            sims = np.where(keep, sims, -np.inf)
        top = np.argsort(-sims)[:k]
        return [(self.ids[i], float(1 - sims[i])) for i in top if np.isfinite(sims[i])]


@lru_cache
def get_vector_store(table: str, url: str | None = None) -> Any:
    from appeal_core.llm.gateway import GatewayEmbeddings

    name = COLLECTIONS[table]
    db = url or get_settings().database_url
    if db.startswith("sqlite"):
        return NumpyVectorStore(name)
    return PGVectorStore(name, GatewayEmbeddings(), db)


def openai_vectors_enabled() -> bool:
    s = get_settings()
    return s.llm_provider == "openai" and s.embedder == "openai"
