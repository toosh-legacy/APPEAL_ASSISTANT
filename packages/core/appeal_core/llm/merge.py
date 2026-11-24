"""Merging a model's extraction answer into the deterministic offline result.

Hosted and local models share this: the offline extractor always runs first, and a model value replaces
an offline value only when it has the right shape. So a bad or partial model answer can never make
extraction worse than the offline baseline, and the output always matches the ExtractedDenial schema.
"""

from __future__ import annotations

import json
from typing import Any

LIST_FIELDS = {"denial_codes"}
# fields the prompt asks the model to copy as written: a value that is not in the letter is a paraphrase or
# an invention, so it is dropped and the offline value kept
QUOTED_FIELDS = {"insurer", "service", "denial_reason"}


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def grounded(v: str, field: str, document: str | None) -> bool:
    """True unless `field` must be quoted and `v` does not occur in `document` (whitespace/case-insensitive)."""
    return document is None or field not in QUOTED_FIELDS or _norm(v) in _norm(document)


def same_shape(v: Any, field: str) -> bool:
    """A list of strings for list fields, otherwise a non-empty string."""
    if field in LIST_FIELDS:
        return isinstance(v, list) and all(isinstance(c, str) for c in v)
    return isinstance(v, str) and bool(v.strip())


def merge_fields(base: dict[str, Any], fields: dict[str, Any], document: str | None = None) -> dict[str, Any]:
    """Overlay model values on `base` (an offline_extract result) where they have the right shape and, for
    quoted fields, occur in `document`. Recomputes missing_fields, plan_type and state."""
    for k, v in fields.items():
        if k in base["fields"] and same_shape(v, k) and (isinstance(v, list) or grounded(v, k, document)):
            base["fields"][k]["value"] = [c.strip() for c in v] if isinstance(v, list) else v.strip()
    base["missing_fields"] = [k for k, f in base["fields"].items() if not f["value"] and k != "denial_codes"]
    base["plan_type"] = base["fields"]["plan_type"]["value"]
    base["state"] = base["fields"]["state"]["value"]
    return base


def merge_model_fields(base: dict[str, Any], model_json: str, document: str | None = None) -> dict[str, Any]:
    """`merge_fields` for a raw JSON answer. Invalid JSON leaves base unchanged."""
    try:
        got = json.loads(model_json)
    except (TypeError, ValueError):
        return base
    if not isinstance(got, dict):
        return base
    inner = got.get("fields")
    return merge_fields(base, inner if isinstance(inner, dict) else got, document)
