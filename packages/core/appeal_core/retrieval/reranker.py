"""Optional second-stage reranker (SPEC 11.3, BLOCKERS "retrieval recall@5").

A local cross-encoder (cross-encoder/ms-marco-MiniLM-L-6-v2, ~90 MB, CPU, no key) reads (query, passage)
pairs and reorders the top-N fused candidates. Selected with RERANKER=crossencoder; the default is
`none`. If the model cannot be loaded, retrieval silently keeps the RRF order (no hard dependency).
"""

from __future__ import annotations

import logging
from functools import lru_cache

log = logging.getLogger(__name__)

MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"
TOP_N = 30  # fixed up front, not tuned on the gold set


class CrossEncoderReranker:
    name = "crossencoder"

    def __init__(self) -> None:
        from sentence_transformers import CrossEncoder

        self.model = CrossEncoder(MODEL_NAME, device="cpu")

    def scores(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        return [float(x) for x in self.model.predict([(query, p) for p in passages], show_progress_bar=False)]


@lru_cache
def get_reranker(kind: str | None = None):
    """Return a reranker or None. `kind` overrides the RERANKER setting (used by the eval ablation)."""
    if kind is None:
        from appeal_core.settings import get_settings

        kind = get_settings().reranker
    if kind in ("", "none", None):
        return None
    if kind == "crossencoder":
        try:
            return CrossEncoderReranker()
        except Exception as e:  # model missing / offline: keep RRF order
            log.warning("reranker unavailable, using RRF order: %s", type(e).__name__)
            return None
    raise ValueError(f"unknown RERANKER={kind}")


def rerank(reranker, query: str, rows: list[dict], text_of, top_n: int = TOP_N) -> list[dict]:
    """Reorder the first top_n rows by cross-encoder score; rows after top_n keep their order."""
    if reranker is None or len(rows) < 2:
        return rows
    head, tail = rows[:top_n], rows[top_n:]
    sc = reranker.scores(query, [text_of(r) for r in head])
    for r, s in zip(head, sc):
        r["rerank_score"] = s
    return sorted(head, key=lambda r: -r["rerank_score"]) + tail
