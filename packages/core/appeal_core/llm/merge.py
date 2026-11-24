"""Merging a model's extraction answer into the deterministic offline result.

Hosted and local models share this: the offline extractor always runs first, and a model value replaces
an offline value only when it has the right shape. So a bad or partial model answer can never make
extraction worse than the offline baseline, and the output always matches the ExtractedDenial schema.
"""

from __future__ import annotations

import json
from typing import Any

LIST_FIELDS = {"denial_codes"}


def same_shape(v: Any, field: str) -> bool:
    """A list of strings for list fields, otherwise a non-empty string."""
    if field in LIST_FIELDS:
        return isinstance(v, list) and all(isinstance(c, str) for c in v)
    return isinstance(v, str) and bool(v.strip())


def merge_model_fields(base: dict[str, Any], model_json: str) -> dict[str, Any]:
    """Overlay valid model values on `base` (an offline_extract result). Invalid JSON leaves base unchanged."""
    try:
        got = json.loads(model_json)
    except (TypeError, ValueError):
        return base
    if not isinstance(got, dict):
        return base
    inner = got.get("fields")
    fields: dict[str, Any] = inner if isinstance(inner, dict) else got
    for k, v in fields.items():
        if k in base["fields"] and same_shape(v, k):
            base["fields"][k]["value"] = [c.strip() for c in v] if isinstance(v, list) else v.strip()
    base["missing_fields"] = [k for k, f in base["fields"].items() if not f["value"] and k != "denial_codes"]
    base["plan_type"] = base["fields"]["plan_type"]["value"]
    base["state"] = base["fields"]["state"]["value"]
    return base
