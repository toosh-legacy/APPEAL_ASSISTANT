"""Reciprocal Rank Fusion: score(d) = sum over lists of 1 / (k + rank_d), rank starting at 1."""

from __future__ import annotations

from collections.abc import Sequence


def rrf(rankings: Sequence[Sequence[str]], k: int = 60, weights: Sequence[float] | None = None) -> list[tuple[str, float]]:
    """Weighted RRF: list i contributes weights[i] / (k + rank)."""
    scores: dict[str, float] = {}
    weights = weights or [1.0] * len(rankings)
    for ranking, w in zip(rankings, weights, strict=True):
        seen = set()
        for rank, doc in enumerate(ranking, start=1):
            if doc in seen:
                continue
            seen.add(doc)
            scores[doc] = scores.get(doc, 0.0) + w / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
