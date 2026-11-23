import math

from appeal_core.retrieval.rrf import rrf
from appeal_core.retrieval.stats import fit_beta_prior, smoothed_rate, wilson
from appeal_evals.retrieval import metrics_for


def test_rrf_formula():
    out = dict(rrf([["a", "b", "c"], ["b", "a"]], k=60))
    assert math.isclose(out["a"], 1 / 61 + 1 / 62)
    assert math.isclose(out["b"], 1 / 62 + 1 / 61)
    assert math.isclose(out["c"], 1 / 63)
    assert rrf([["x", "y"], ["y"]])[0][0] == "y"


def test_rrf_ignores_duplicates_within_a_list():
    assert dict(rrf([["a", "a", "b"]]))["a"] == 1 / 61


def test_wilson_interval():
    lo, hi = wilson(50, 100)
    assert math.isclose(lo, 0.4038, abs_tol=1e-3) and math.isclose(hi, 0.5962, abs_tol=1e-3)
    assert wilson(0, 0) == (0.0, 1.0)
    lo, hi = wilson(0, 10)
    assert lo == 0.0 and 0.2 < hi < 0.35


def test_eb_shrinks_small_groups():
    a, b = fit_beta_prior([50, 5, 1], [100, 10, 1])
    prior = a / (a + b)
    assert abs(smoothed_rate(1, 1, a, b) - prior) < abs(1.0 - prior)


def test_retrieval_metrics():
    m = metrics_for(["x", "a", "y", "b"], {"a", "b"})
    assert m["recall@5"] == 1.0 and m["mrr"] == 0.5
    assert metrics_for(["x"], {"a"}) == {"recall@5": 0.0, "mrr": 0.0, "ndcg@10": 0.0}


# ---------------------------------------------------------------- diversification + reranker (no DB, no model)
def _row(i, kind="regulation", heading="§ 1 Claims procedure.", topics=()):
    return {"id": i, "source_kind": kind, "heading": heading, "text": f"text {i}", "topics": list(topics)}


def _div(ordered, query="how do I appeal", k=5, required=()):
    from appeal_core.retrieval.retriever import diversify_rules

    rows = {r["id"]: r for r in ordered}
    return [r["id"] for r in diversify_rules(ordered, rows, {}, query, k, list(required))]


def test_at_most_one_summary_and_forced_items_keep_rank():
    ordered = [_row("s1", "summary"), _row("s2", "summary"), _row("r1"), _row("r2"), _row("s3", "summary"), _row("r3"), _row("p1", topics=["deadlines"])]
    out = _div(ordered)
    assert sum(i.startswith("s") for i in out) == 1
    assert out[0] == "s1"  # the summary keeps its natural (first) rank
    assert "p1" in out and out[-1] == "p1"  # procedural chunk guaranteed, but not pinned to the top


def test_required_ids_come_first():
    ordered = [_row("r1"), _row("r2"), _row("d1", topics=["deadlines"])]
    assert _div(ordered, required=["d1"])[0] == "d1"


def test_definitions_demoted_unless_asked():
    ordered = [_row("def", heading="§ 422.561 Definitions."), _row("r1"), _row("r2")]
    assert _div(ordered, k=3)[0] == "r1"
    assert _div(ordered, query="what counts as an organization determination", k=3)[0] == "def"


def test_rerank_reorders_head_only_and_none_is_noop():
    from appeal_core.retrieval.reranker import rerank

    class Fake:
        def scores(self, q, passages):
            return [len(p) for p in passages]

    rows = [{"id": "a", "t": "x"}, {"id": "b", "t": "xxx"}, {"id": "c", "t": "xx"}, {"id": "d", "t": "xxxxxx"}]
    out = rerank(Fake(), "q", [dict(r) for r in rows], lambda r: r["t"], top_n=3)
    assert [r["id"] for r in out] == ["b", "c", "a", "d"]
    assert rerank(None, "q", rows, lambda r: r["t"]) is rows


def test_unknown_reranker_rejected():
    import pytest
    from appeal_core.retrieval.reranker import get_reranker

    assert get_reranker("none") is None
    with pytest.raises(ValueError):
        get_reranker("bogus")
