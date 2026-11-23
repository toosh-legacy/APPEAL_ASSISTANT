"""Embed kb_chunk and precedent_chunk rows that have no embedding yet (idempotent)."""

from __future__ import annotations

import time

import numpy as np
from appeal_core.db import get_engine
from sqlalchemy import text

from appeal_data.common import log_blocker, update_manifest


def _embedder():
    import os

    from appeal_core.retrieval import embedder as E

    if os.environ.get("EMBEDDER") == "lsa":
        with get_engine().connect() as c:
            corpus = [r[0] for r in c.execute(text("SELECT text FROM kb_chunk UNION ALL SELECT text FROM precedent_chunk"))]
        return E.LSAEmbedder.fit(corpus)
    try:
        return E.MiniLMEmbedder()
    except Exception as e:
        log_blocker(
            "MiniLM embedding model unavailable",
            f"sentence-transformers download of {E.MODEL_NAME} failed: {e}",
            "TF-IDF + truncated SVD (LSA) 384-d embeddings fitted on the corpus (EMBEDDER=lsa)",
            "Re-run `make data` with network access to switch back to MiniLM.",
        )
        with get_engine().connect() as c:
            corpus = [r[0] for r in c.execute(text("SELECT text FROM kb_chunk UNION ALL SELECT text FROM precedent_chunk"))]
        return E.LSAEmbedder.fit(corpus)


def _lit(v: np.ndarray) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def run(force: bool = False, batch: int = 512) -> dict:
    eng = get_engine()
    if force:
        with eng.begin() as c:
            c.execute(text("UPDATE kb_chunk SET embedding=NULL"))
            c.execute(text("UPDATE precedent_chunk SET embedding=NULL"))
    with eng.connect() as c:
        todo = {
            "kb_chunk": c.execute(text("SELECT count(*) FROM kb_chunk WHERE embedding IS NULL")).scalar(),
            "precedent_chunk": c.execute(text("SELECT count(*) FROM precedent_chunk WHERE embedding IS NULL")).scalar(),
        }
    if not any(todo.values()):
        print("[embed] nothing to embed")
        return {"embedded": 0}
    emb = _embedder()
    total = 0
    t0 = time.time()
    for table, textcol in [("kb_chunk", "coalesce(heading,'') || ' ' || text"), ("precedent_chunk", "coalesce(treatment_category,'') || ' ' || coalesce(treatment_subcategory,'') || '. ' || text")]:
        while True:
            with eng.connect() as c:
                rows = c.execute(text(f"SELECT id, {textcol} FROM {table} WHERE embedding IS NULL ORDER BY id LIMIT :b"), {"b": batch}).all()
            if not rows:
                break
            vecs = emb.embed([r[1] for r in rows])
            with eng.begin() as c:
                c.execute(text(f"UPDATE {table} SET embedding = CAST(:v AS vector) WHERE id = :id"), [{"v": _lit(v), "id": r[0]} for r, v in zip(rows, vecs, strict=True)])
            total += len(rows)
            if total % (batch * 10) == 0:
                print(f"[embed] {total} rows, {total / (time.time() - t0):.0f}/s", flush=True)
    update_manifest("embeddings", embedder=emb.name, dim=emb.dim, rows=total, source="local")
    print(f"[embed] embedded {total} rows with {emb.name} in {time.time() - t0:.0f}s")
    return {"embedded": total, "embedder": emb.name}
