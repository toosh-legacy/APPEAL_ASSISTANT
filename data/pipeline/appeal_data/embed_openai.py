"""Index kb_chunk and precedent_chunk with OpenAI text-embedding-3-small into PGVector (idempotent).

    LLM_PROVIDER=openai uv run python -m appeal_data.embed_openai [--table kb_chunk] [--limit N]

Embedding calls go through the LiteLLM gateway, so they are priced into the spend ledger and stop at the
session budget (LLM_SESSION=index by default here). ~17M tokens for all 52,610 precedent chunks ≈ $0.35.
"""

from __future__ import annotations

import argparse
import os
import time

from sqlalchemy import text

COLS = {
    "kb_chunk": "SELECT id, coalesce(heading, '') || '. ' || text AS t, source_kind, plan_types, citation_path FROM kb_chunk",
    "precedent_chunk": "SELECT id, text AS t, treatment_category, treatment_subcategory, type, year, overturned, reference_id FROM precedent_chunk",
}


def index(table: str, batch: int = 256, limit: int | None = None) -> int:
    from appeal_core.db import get_engine
    from appeal_core.llm.cost import get_ledger
    from appeal_core.llm.gateway import GatewayEmbeddings
    from appeal_core.retrieval.vectorstore import get_vector_store

    store = get_vector_store(table)
    have = store.existing_ids()
    with get_engine().connect() as c:
        rows = [r._mapping for r in c.execute(text(COLS[table] + " ORDER BY id"))]
    todo = [dict(r) for r in rows if r["id"] not in have][: limit or None]
    emb = GatewayEmbeddings()
    done, t0 = 0, time.time()
    for i in range(0, len(todo), batch):
        chunk = todo[i : i + batch]
        texts = [r["t"][:24000] for r in chunk]  # well under the 8,192-token input limit
        vecs = emb.embed_documents(texts)
        metas = [{k: v for k, v in r.items() if k not in ("id", "t")} for r in chunk]
        store.add([r["id"] for r in chunk], vecs, texts, metas)
        done += len(chunk)
        if (i // batch) % 20 == 0:
            print(f"{table}: {done}/{len(todo)} in {time.time() - t0:.0f}s, spent ${get_ledger().spent:.4f}", flush=True)
    store.ensure_index()
    print(f"{table}: indexed {done} (already had {len(have)}); ledger {get_ledger().summary()}", flush=True)
    return done


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", choices=list(COLS), action="append")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    os.environ.setdefault("LLM_SESSION", "index")
    from appeal_data.common import update_manifest

    for t in a.table or list(COLS):
        n = index(t, limit=a.limit)
        update_manifest(f"embeddings_openai_{t}", embedder="text-embedding-3-small", dim=1536, rows_added=n, source="openai via LiteLLM")


if __name__ == "__main__":
    main()
