"""Loaders for packages/kb: rights summaries, playbooks, denial codes and deadline rules."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from appeal_core.settings import ROOT

KB = ROOT / "packages" / "kb"
REG_CHUNKS = ROOT / "data" / "processed" / "regulation_chunks.json"

CATEGORIES = [
    "medical_necessity",
    "prior_authorization",
    "out_of_network",
    "coding_billing_error",
    "experimental_investigational",
    "not_covered_benefit",
    "timely_filing",
    "other_unclear",
]
PLAN_TYPES = [
    "employer_self_funded",
    "employer_fully_insured",
    "individual_marketplace",
    "medicare_advantage",
    "medicaid_managed_care",
]


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def parse_summary(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
    if not m:
        raise ValueError(f"{path} has no front matter")
    meta = yaml.safe_load(m.group(1))
    body = m.group(2)
    sections = []
    for sm in re.finditer(r"^## (.+?)\n(.*?)(?=^## |\Z)", body, re.S | re.M):
        heading, text = sm.group(1).strip(), sm.group(2).strip()
        sections.append(
            {
                "id": f"sum:{meta['id']}#{_slug(heading)}",
                "source_id": f"sum:{meta['id']}",
                "source_kind": "summary",
                "citation_path": f"Rights summary: {meta['title']}",
                "heading": f"{meta['title']} > {heading}",
                "text": text,
                "plan_types": meta["plan_types"],
                "topics": [],
                "status": meta.get("status", "needs_human_review"),
                "sources": meta.get("sources", []),
                "url": None,
            }
        )
    return meta, sections


@lru_cache
def summary_chunks() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in sorted((KB / "summaries").glob("*.md")):
        _, secs = parse_summary(p)
        out.extend(secs)
    return out


@lru_cache
def playbooks() -> dict[str, dict[str, Any]]:
    return {p.stem: yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted((KB / "playbooks").glob("*.yaml"))}


@lru_cache
def denial_codes() -> dict[str, str]:
    data = yaml.safe_load((KB / "denial_codes.yaml").read_text(encoding="utf-8"))
    return {c["code"]: c["category"] for c in data["codes"]}


@lru_cache
def denial_code_descriptions() -> dict[str, str]:
    data = yaml.safe_load((KB / "denial_codes.yaml").read_text(encoding="utf-8"))
    return {c["code"]: c["description"] for c in data["codes"]}


@lru_cache
def regulation_chunks() -> list[dict[str, Any]]:
    if not REG_CHUNKS.exists():
        return []
    return json.loads(REG_CHUNKS.read_text(encoding="utf-8"))


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("’", "'")).lower()


def find_chunk(source_id: str, must_contain: str, chunks: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    needle = _norm(must_contain)
    for c in chunks if chunks is not None else regulation_chunks():
        if c["source_id"] == source_id and needle in _norm(c["text"]):
            return c
    return None


@lru_cache
def deadline_rules() -> dict[str, Any]:
    """Deadline rules with their basis chunk resolved. Unresolved rules are marked disabled (hard rule 3)."""
    data = yaml.safe_load((KB / "deadlines.yaml").read_text(encoding="utf-8"))
    chunks = regulation_chunks()
    for group in ("rules", "next_levels"):
        for r in data[group]:
            c = find_chunk(r["source_id"], r["must_contain"], chunks)
            r["basis_chunk_id"] = c["id"] if c else None
            r["basis_citation"] = c["citation_path"] if c else None
            r["enabled"] = c is not None
            if r.get("also_cites_source"):
                c2 = find_chunk(r["also_cites_source"], r["also_must_contain"], chunks)
                r["also_chunk_id"] = c2["id"] if c2 else None
                r["enabled"] = r["enabled"] and c2 is not None
    return data
