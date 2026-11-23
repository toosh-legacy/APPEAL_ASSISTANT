"""Proportion statistics: Wilson interval and empirical-Bayes (beta-binomial) smoothing."""

from __future__ import annotations

import math


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def fit_beta_prior(ks: list[int], ns: list[int]) -> tuple[float, float]:
    """Method-of-moments beta prior from group rates (weighted), clipped to sane values."""
    rates = [k / n for k, n in zip(ks, ns) if n > 0]
    weights = [n for n in ns if n > 0]
    if not rates:
        return (1.0, 1.0)
    tot = sum(weights)
    m = sum(r * w for r, w in zip(rates, weights)) / tot
    v = sum(w * (r - m) ** 2 for r, w in zip(rates, weights)) / tot
    avg_n = tot / len(weights)
    v_between = max(v - m * (1 - m) / avg_n, 1e-4)
    common = m * (1 - m) / v_between - 1
    common = min(max(common, 2.0), 500.0)
    return (m * common, (1 - m) * common)


def smoothed_rate(k: int, n: int, alpha: float, beta: float) -> float:
    return (k + alpha) / (n + alpha + beta)
