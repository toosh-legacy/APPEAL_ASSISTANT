"""Similar-case statistics from imr_stats (F6): empirical overturn rate with a Wilson 95% interval, N,
and the trend by year. Falls back from subcategory to category when N is small."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from appeal_core.db import get_engine
from appeal_core.retrieval.stats import wilson

MIN_N = 20


def get_stats(treatment_category: str | None, treatment_subcategory: str | None = None, diagnosis_category: str | None = None, url: str | None = None) -> dict[str, Any]:
    if not treatment_category:
        return {"scope": "unknown", "n": 0, "overturned_n": 0, "enough_data": False, "by_year": []}
    attempts = []
    if treatment_subcategory and diagnosis_category:
        attempts.append(("treatment_category = :tc AND treatment_subcategory = :tsc AND diagnosis_category = :dc", f"{treatment_category} / {treatment_subcategory} / {diagnosis_category}"))
    if treatment_subcategory:
        attempts.append(("treatment_category = :tc AND treatment_subcategory = :tsc", f"{treatment_category} / {treatment_subcategory}"))
    attempts.append(("treatment_category = :tc", treatment_category))
    params = {"tc": treatment_category, "tsc": treatment_subcategory, "dc": diagnosis_category}
    with get_engine(url).connect() as c:
        for where, scope in attempts:
            w = where
            rows = c.execute(
                text(f"SELECT year, sum(n) AS n, sum(overturned_n) AS k FROM imr_stats WHERE {w} GROUP BY year ORDER BY year"),
                params,
            ).all()
            n = int(sum(r.n for r in rows))
            k = int(sum(r.k for r in rows))
            if n >= MIN_N or where == attempts[-1][0]:
                lo, hi = wilson(k, n)
                return {
                    "scope": scope,
                    "n": n,
                    "overturned_n": k,
                    "rate": (k / n) if n >= MIN_N else None,
                    "ci_low": lo if n >= MIN_N else None,
                    "ci_high": hi if n >= MIN_N else None,
                    "by_year": [{"year": int(r.year), "n": int(r.n), "overturned_n": int(r.k)} for r in rows],
                    "enough_data": n >= MIN_N,
                }
    return {"scope": treatment_category, "n": 0, "overturned_n": 0, "enough_data": False, "by_year": []}
