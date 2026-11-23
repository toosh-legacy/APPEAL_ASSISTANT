"""Hybrid retriever (SPEC 11.3): query variants -> Postgres full-text (ts_rank_cd) top 50 + pgvector
cosine top 50 (with metadata filters) -> Reciprocal Rank Fusion (k=60) -> diversification."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text

from appeal_core.db import get_engine
from appeal_core.retrieval.reranker import get_reranker, rerank
from appeal_core.retrieval.rrf import rrf

_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9.\-]*")


def or_query(q: str) -> str:
    """websearch_to_tsquery syntax with OR between terms (AND is too strict for natural-language queries)."""
    words = [w for w in _WORD.findall(q) if len(w) > 1]
    return " or ".join(words) if words else q


_ASKS_DEFINITION = re.compile(r"\b(defin\w*|mean\w*|what (is|are|counts))\b", re.I)
PROCEDURAL = {"deadlines", "external_review"}


def _is_definitions(r: dict) -> bool:
    return "definition" in (r.get("heading") or "").lower()


def diversify_rules(ordered: list[dict], rows: dict, score: dict, query: str, k: int, required_ids: list[str]) -> list[dict]:
    """SPEC 11.3 step 5 for rules.

    - required ids (deadline basis chunks) always come first, so deadlines are citable;
    - at least one procedural-rights chunk and exactly one rights summary are guaranteed, but forced items keep
      their natural rank instead of being pinned to the top;
    - at most one summary: summaries paraphrase the rules, and the Writer cites regulation paragraphs;
    - "Definitions" sections go to the back unless the question asks what something means (they mention every
      term, so they win keyword and vector matches without answering the question).
    """
    pool = list(ordered)
    if not _ASKS_DEFINITION.search(query):
        pool = [r for r in pool if not _is_definitions(r)] + [r for r in pool if _is_definitions(r)]
    pos = {r["id"]: i for i, r in enumerate(pool)}
    req: list[dict] = []
    for rid in required_ids:
        if rid in rows and rid not in [o["id"] for o in req]:
            rr = dict(rows[rid])
            rr["score"] = score.get(rid, 0.0)
            req.append(rr)
    chosen: dict[str, dict] = {}
    if not any(set(o.get("topics") or []) & PROCEDURAL for o in req):
        r = next((r for r in pool if set(r.get("topics") or []) & PROCEDURAL), None)
        if r:
            chosen[r["id"]] = r
    has_summary = any(o["source_kind"] == "summary" for o in req)
    if not has_summary:
        r = next((r for r in pool if r["source_kind"] == "summary"), None)
        if r:
            chosen[r["id"]] = r
            has_summary = True
    req_ids = {o["id"] for o in req}
    for r in pool:
        if len(req) + len(chosen) >= k:
            break
        if r["id"] in req_ids or r["id"] in chosen:
            continue
        if r["source_kind"] == "summary" and has_summary:
            continue
        chosen[r["id"]] = r
    rest = sorted(chosen.values(), key=lambda r: pos.get(r["id"], 1 << 30))
    return (req + rest)[:k]


class HybridRetriever:
    def __init__(self, url: str | None = None, embedder=None, mode: str = "hybrid", reranker: str | None = None):
        self.url = url
        self._embedder = embedder
        self.mode = mode  # keyword | vector | hybrid
        self.reranker_kind = reranker  # None = RERANKER setting; "none" | "crossencoder"

    @property
    def reranker(self):
        return get_reranker(self.reranker_kind)

    @property
    def embedder(self):
        if self._embedder is None:
            from appeal_core.retrieval.embedder import get_embedder

            self._embedder = get_embedder()
        return self._embedder

    # ------------------------------------------------------------------ low-level searches
    def _kw(self, table: str, q: str, where: str, params: dict, limit: int = 50) -> list[str]:
        sql = f"""
            SELECT id FROM {table}
            WHERE tsv @@ websearch_to_tsquery('english', :q) {where}
            ORDER BY ts_rank_cd(tsv, websearch_to_tsquery('english', :q)) DESC, id
            LIMIT :lim
        """
        with get_engine(self.url).connect() as c:
            return [r[0] for r in c.execute(text(sql), {"q": or_query(q), "lim": limit, **params})]

    def _vec(self, table: str, q: str, where: str, params: dict, limit: int = 50) -> list[str]:
        vec = self.embedder.embed([q])[0]
        lit = "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
        sql = f"""
            SELECT id FROM {table}
            WHERE embedding IS NOT NULL {where}
            ORDER BY embedding <=> CAST(:v AS vector), id
            LIMIT :lim
        """
        with get_engine(self.url).connect() as c:
            c.execute(text("SET LOCAL hnsw.ef_search = 100"))
            return [r[0] for r in c.execute(text(sql), {"v": lit, "lim": limit, **params})]

    def _ranked(self, table: str, queries: list[str], where: str, params: dict, mode: str | None = None) -> list[tuple[str, float]]:
        mode = mode or self.mode
        lists: list[list[str]] = []
        weights: list[float] = []
        for i, q in enumerate(queries):
            # The first query counts most. Rewrites only feed the vector side at low weight: appended legal
            # vocabulary helps semantic matching but floods OR-keyword search (see retrieval_ablation.md).
            w = 1.0 if i == 0 else 0.25
            if mode in ("keyword", "hybrid") and (i == 0 or mode == "keyword"):
                lists.append(self._kw(table, q, where, params))
                weights.append(w)
            if mode in ("vector", "hybrid"):
                try:
                    lists.append(self._vec(table, q, where, params))
                    weights.append(w)
                except Exception:
                    if mode == "vector":
                        raise
        return rrf(lists, k=60, weights=weights)

    # ------------------------------------------------------------------ rules
    def search_rules(
        self,
        queries: list[str],
        plan_type: str | None = None,
        k: int = 8,
        mode: str | None = None,
        diversify: bool = True,
        required_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        where, params = "", {}
        if plan_type:
            where = "AND plan_types @> CAST(:pt AS jsonb)"
            params = {"pt": f'["{plan_type}"]'}
        ranked = self._ranked("kb_chunk", queries, where, params, mode)
        ids = [i for i, _ in ranked[:50]]
        rows = self._fetch_kb(ids + (required_ids or []))
        score = dict(ranked)
        ordered = [rows[i] for i in ids if i in rows]
        for r in ordered:
            r["score"] = score.get(r["id"], 0.0)
        ordered = rerank(self.reranker, queries[0], ordered, lambda r: f"{r.get('heading') or ''}. {r['text']}")
        if not diversify:
            return ordered[:k]
        return diversify_rules(ordered, rows, score, queries[0], k, required_ids or [])

    def _fetch_kb(self, ids: list[str]) -> dict[str, dict]:
        if not ids:
            return {}
        sql = text(
            "SELECT id, source_kind, citation_path, heading, text, plan_types, topics, status, url FROM kb_chunk WHERE id = ANY(:ids)"
        )
        with get_engine(self.url).connect() as c:
            return {r.id: dict(r._mapping) for r in c.execute(sql, {"ids": list(set(ids))})}

    # ------------------------------------------------------------------ precedents
    def search_precedents(
        self,
        queries: list[str],
        treatment_category: str | None = None,
        treatment_subcategory: str | None = None,
        imr_type: str | None = None,
        k: int = 5,
        mode: str | None = None,
        diversify: bool = True,
    ) -> list[dict[str, Any]]:
        where, params = "", {}
        if treatment_category:
            where += " AND treatment_category = :tc"
            params["tc"] = treatment_category
        if imr_type:
            where += " AND type = :ty"
            params["ty"] = imr_type
        ranked = self._ranked("precedent_chunk", queries, where, params, mode)
        if len(ranked) < k and (treatment_category or imr_type):  # relax filters
            ranked = self._ranked("precedent_chunk", queries, "", {}, mode)
        ids = [i for i, _ in ranked[:100]]
        rows = self._fetch_prec(ids)
        score = dict(ranked)
        ordered = []
        seen_ref = set()
        for i in ids:
            r = rows.get(i)
            if not r or r["reference_id"] in seen_ref:
                continue
            seen_ref.add(r["reference_id"])
            r["score"] = score[i]
            # prefer same subcategory and recent years
            bonus = 0.0
            if treatment_subcategory and r["treatment_subcategory"] == treatment_subcategory:
                bonus += 0.004
            bonus += max(0, r["year"] - 2015) * 0.0002
            r["rank_score"] = r["score"] + (bonus if diversify else 0.0)
            ordered.append(r)
        ordered.sort(key=lambda r: -r["rank_score"])
        ordered = rerank(self.reranker, queries[0], ordered, lambda r: r["text"])
        if not diversify:
            return ordered[:k]
        out = ordered[: max(1, k - 1)]
        # include both outcomes
        for want in (True, False):
            if not any(o["overturned"] == want for o in out):
                for r in ordered:
                    if r["overturned"] == want and r not in out:
                        out.append(r)
                        break
        for r in ordered:
            if len(out) >= k:
                break
            if r not in out:
                out.append(r)
        return out[:k]

    def _fetch_prec(self, ids: list[str]) -> dict[str, dict]:
        if not ids:
            return {}
        sql = text(
            """SELECT id, reference_id, text, year, treatment_category, treatment_subcategory, diagnosis_category,
                      type, overturned FROM precedent_chunk WHERE id = ANY(:ids)"""
        )
        with get_engine(self.url).connect() as c:
            return {r.id: dict(r._mapping) for r in c.execute(sql, {"ids": ids})}


def get_retriever(mode: str = "hybrid", url: str | None = None):
    from appeal_core.settings import get_settings

    b = get_settings().retriever_backend
    if b == "postgres":
        return HybridRetriever(url=url, mode=mode)
    if b == "azure":
        from appeal_core.adapters.azure import AzureSearchRetriever

        return AzureSearchRetriever()
    raise ValueError(f"unknown RETRIEVER_BACKEND={b}")
