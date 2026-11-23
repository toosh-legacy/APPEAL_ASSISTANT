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
